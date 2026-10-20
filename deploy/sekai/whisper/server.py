"""Memory-only, offline, CPU Whisper sidecar. Run exactly one ASGI worker."""

import asyncio
import io
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Literal

import av
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from faster_whisper import WhisperModel

MAX_BYTES = 5 * 1024 * 1024
SAMPLE_RATE = 16000
MAX_SAMPLES = 30 * SAMPLE_RATE
MAX_TEXT = 4000
MIME_TYPES = {"audio/webm", "audio/mp4", "audio/wav", "audio/x-wav", "audio/ogg", "audio/mpeg", "audio/flac"}
FORMATS = "matroska,webm,mov,mp4,m4a,3gp,3g2,mj2,wav,ogg,flac,mp3"


def decode_bounded(data: bytes) -> np.ndarray:
    """Decode incrementally; never give an unbounded file to decode_audio()."""
    deadline = time.monotonic() + 10
    chunks: list[np.ndarray] = []
    samples = 0

    def collect(frames: list[av.AudioFrame]) -> None:
        nonlocal samples
        for frame in frames:
            samples += frame.samples
            if samples > MAX_SAMPLES:
                raise HTTPException(422, "录音不能超过30秒")
            chunks.append(frame.to_ndarray().reshape(-1))

    try:
        # Disable nested protocols/playlists: only the supplied in-memory container.
        with av.open(io.BytesIO(data), options={
            "protocol_whitelist": "pipe", "format_whitelist": FORMATS,
        }) as container:
            if len(container.streams.audio) != 1:
                raise HTTPException(422, "请提供单段音频")
            stream = container.streams.audio[0]
            stream.thread_count = 1
            if (stream.duration is not None and stream.time_base is not None
                    and stream.duration * stream.time_base > 30):
                raise HTTPException(422, "录音不能超过30秒")
            resampler = av.AudioResampler(format="flt", layout="mono", rate=SAMPLE_RATE)
            for frame in container.decode(stream):
                if time.monotonic() > deadline:
                    raise HTTPException(422, "音频解码超时，请重新录音")
                # Check before conversion and reject pathological channel layouts.
                if (not frame.sample_rate or frame.samples > frame.sample_rate * 30
                        or len(frame.layout.channels) > 8):
                    raise HTTPException(422, "音频格式不受支持")
                frame.pts = None
                collect(resampler.resample(frame))
            collect(resampler.resample(None))
    except (av.FFmpegError, ValueError, OverflowError):
        raise HTTPException(422, "音频损坏或格式不受支持") from None
    if not samples:
        raise HTTPException(422, "录音没有音频内容")
    return np.concatenate(chunks)


class Transcriber:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.model: WhisperModel | None = None

    def load(self) -> None:
        self.model = WhisperModel(
            os.environ.get("WHISPER_MODEL_PATH", "/models/small"),
            device="cpu", compute_type="int8", cpu_threads=4,
            num_workers=1, local_files_only=True,
        )

    def transcribe(self, data: bytes, language: str) -> dict[str, str]:
        """The actual worker owns the lock until it finishes, even after cancellation."""
        try:
            audio = decode_bounded(data)
            if self.model is None:
                raise HTTPException(503, "语音输入服务尚未就绪")
            segments, info = self.model.transcribe(
                audio, language=None if language == "auto" else language,
                vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
                beam_size=1, best_of=1, temperature=0, max_new_tokens=256,
                condition_on_previous_text=False, log_progress=False,
            )
            text = ""
            for segment in segments:
                text += segment.text
                if len(text) > MAX_TEXT or len(text.encode()) > MAX_TEXT * 4:
                    raise HTTPException(422, "识别结果过长，请缩短录音")
            return {"text": text.strip(), "language": info.language}
        except HTTPException:
            raise
        except Exception:
            # Never expose model paths, decoder errors, audio or transcription in logs.
            raise HTTPException(503, "语音输入服务暂时不可用") from None
        finally:
            self.lock.release()


def create_app(transcriber: Transcriber | None = None) -> FastAPI:
    worker = transcriber or Transcriber()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await asyncio.get_running_loop().run_in_executor(executor, worker.load)
            yield
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health() -> dict:
        if worker.model is None:
            raise HTTPException(503, "语音输入服务尚未就绪")
        return {"ready": True}

    @app.post("/transcribe")
    async def transcribe(
        request: Request, language: Literal["auto", "zh", "ja"] = "auto",
    ) -> dict:
        if worker.model is None:
            raise HTTPException(503, "语音输入服务尚未就绪")
        if request.headers.get("content-type", "").split(";", 1)[0].lower() not in MIME_TYPES:
            raise HTTPException(415, "音频格式不受支持")
        if not worker.lock.acquire(blocking=False):
            raise HTTPException(429, "语音输入正在处理，请稍后再试", headers={"Retry-After": "3"})
        handed_off = False
        try:
            data = bytearray()
            async with asyncio.timeout(15):
                async for chunk in request.stream():
                    if len(data) + len(chunk) > MAX_BYTES:
                        raise HTTPException(413, "录音不能超过5MiB")
                    data.extend(chunk)
            if not data:
                raise HTTPException(422, "录音为空")
            future = asyncio.get_running_loop().run_in_executor(
                executor, worker.transcribe, bytes(data), language,
            )
            handed_off = True
            # Retrieve errors even if the awaiting HTTP request has been cancelled.
            future.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
            return await asyncio.shield(future)
        except TimeoutError:
            raise HTTPException(408, "录音上传超时") from None
        finally:
            if not handed_off:
                worker.lock.release()

    @app.middleware("http")
    async def no_cache(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return app


app = create_app()
