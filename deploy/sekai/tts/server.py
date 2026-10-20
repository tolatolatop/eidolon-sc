"""Offline CPU Kokoro, memory-only synthesis. Run exactly one ASGI worker."""

import asyncio
import io
import json
import logging
import threading
import time
import unicodedata
import wave
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response

SAMPLE_RATE = 24000
MAX_SAMPLES = 60 * SAMPLE_RATE
MAX_BODY_BYTES = 4096
MAX_TEXT = 300
MAX_TEXT_BYTES = 1200
MAX_PHONEMES = 2400
CHUNK_PHONEMES = 400
MAX_CHUNKS = 12
MODEL_PATH = Path("/models/kokoro-v1.0.int8.onnx")
VOICES_PATH = Path("/models/voices-v1.0.bin")
DICT_FILES = ("sys.dic", "unk.dic", "matrix.bin", "char.bin", "dicrc", "mecabrc")
Language = Literal["ja", "zh-cn"]


def local_assets() -> Path:
    """Use only unidic-lite's packaged dictionary; no download path exists."""
    import unidic_lite

    dictionary = Path(unidic_lite.DICDIR)
    for path in (MODEL_PATH, VOICES_PATH, *(dictionary / name for name in DICT_FILES)):
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError("本地朗读模型或词典不完整")
    return dictionary


def unique_fields(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def phoneme_chunks(converter, text: str, vocabulary: dict) -> list[str]:
    """G2P the whole bounded reply once, preserving words across former cut points."""
    raw, _ = converter(text)
    phonemes = " ".join(raw.split())
    if not phonemes:
        raise HTTPException(422, "没有可合成的语音")
    if len(phonemes) > MAX_PHONEMES:
        raise HTTPException(422, "回复音素过长，请选择较短回复")
    if any(symbol not in vocabulary for symbol in phonemes):
        raise HTTPException(422, "回复包含当前音色不支持的读音，请选择其他回复")
    chunks = [phonemes[i:i + CHUNK_PHONEMES] for i in range(0, len(phonemes), CHUNK_PHONEMES)]
    if len(chunks) > MAX_CHUNKS:
        raise HTTPException(422, "回复分段过多，请选择较短回复")
    return chunks


def parse_body(data: bytes) -> tuple[str, Language]:
    try:
        body = json.loads(data.decode("utf-8"), object_pairs_hook=unique_fields)
        if not isinstance(body, dict) or set(body) != {"text", "language"}:
            raise ValueError
        text, language = body["text"], body["language"]
        if (not isinstance(text, str) or language not in ("ja", "zh-cn")
                or not text.strip() or len(text) > MAX_TEXT
                or len(text.encode("utf-8")) > MAX_TEXT_BYTES
                or any(unicodedata.category(c) in {"Cc", "Cs"} and c not in "\n\t" for c in text)):
            raise ValueError
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise HTTPException(422, "请提供300字以内的日语或中文朗读文字") from None
    return text.strip(), language


def pcm_wav(parts: list[np.ndarray]) -> bytes:
    if not parts:
        raise HTTPException(422, "没有可合成的语音")
    audio = np.concatenate(parts)
    if audio.ndim != 1 or not 0 < audio.size <= MAX_SAMPLES or not np.isfinite(audio).all():
        raise HTTPException(503, "本地朗读返回了无效音频")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return output.getvalue()


class Synthesizer:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.model = None
        self.g2p = {}

    def load(self) -> None:
        local_assets()
        # Imports intentionally follow the complete local-file check.
        import jieba
        import onnxruntime as ort
        from kokoro_onnx import Kokoro
        from misaki import zh
        from misaki.cutlet import Cutlet

        logging.getLogger("kokoro_onnx").disabled = True  # DEBUG logs contain phonemes.
        jieba.setLogLevel(logging.ERROR)
        jieba.dt.tmp_dir = "/tmp"
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        session = ort.InferenceSession(str(MODEL_PATH), sess_options=options, providers=["CPUExecutionProvider"])
        model = Kokoro.from_session(session, str(VOICES_PATH))
        self.g2p = {"ja": Cutlet(), "zh-cn": zh.ZHG2P()}
        # Warm up only public fixed text. No user text, phonemes or audio are logged.
        for language, text in (("ja", "こんにちは。"), ("zh-cn", "你好。")):
            chunks = phoneme_chunks(self.g2p[language], text, model.tokenizer.vocab)
            parts = []
            for phonemes in chunks:
                audio, rate = model.create(phonemes, voice="jf_alpha" if language == "ja" else "zf_xiaobei", is_phonemes=True)
                if rate != SAMPLE_RATE:
                    raise RuntimeError("本地朗读采样率无效")
                parts.append(audio)
            pcm_wav(parts)
        self.model = model

    def synthesize(self, text: str, language: Language) -> bytes:
        """The actual native worker owns the lock, including after HTTP cancellation."""
        try:
            if self.model is None:
                raise HTTPException(503, "本地朗读服务尚未就绪")
            deadline = time.monotonic() + 90
            chunks = phoneme_chunks(self.g2p[language], text, self.model.tokenizer.vocab)
            parts = []
            samples = 0
            for chunk in chunks:
                if time.monotonic() > deadline:
                    raise HTTPException(503, "本地朗读处理超时")
                audio, rate = self.model.create(chunk, voice="jf_alpha" if language == "ja" else "zf_xiaobei", is_phonemes=True)
                if rate != SAMPLE_RATE or audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
                    raise HTTPException(503, "本地朗读返回了无效音频")
                samples += audio.size
                if samples > MAX_SAMPLES:
                    raise HTTPException(422, "朗读不能超过60秒")
                parts.append(audio)
            return pcm_wav(parts)
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001 - never leak G2P text or native errors
            raise HTTPException(503, "本地朗读服务暂时不可用") from None
        finally:
            self.lock.release()


def create_app(synthesizer: Synthesizer | None = None) -> FastAPI:
    worker = synthesizer or Synthesizer()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kokoro")

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
            raise HTTPException(503, "本地朗读服务尚未就绪")
        return {"ready": True}

    @app.post("/synthesize")
    async def synthesize(request: Request) -> Response:
        if worker.model is None:
            raise HTTPException(503, "本地朗读服务尚未就绪")
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise HTTPException(415, "请提供JSON请求")
        if not worker.lock.acquire(blocking=False):
            raise HTTPException(429, "本地朗读正在处理，请稍后再试", headers={"Retry-After": "3"})
        handed_off = False
        try:
            data = bytearray()
            async with asyncio.timeout(15):
                async for chunk in request.stream():
                    if len(data) + len(chunk) > MAX_BODY_BYTES:
                        raise HTTPException(413, "朗读请求过长")
                    data.extend(chunk)
            text, language = parse_body(bytes(data))
            future = asyncio.get_running_loop().run_in_executor(executor, worker.synthesize, text, language)
            handed_off = True
            future.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
            async with asyncio.timeout(95):
                return Response(await asyncio.shield(future), media_type="audio/wav")
        except TimeoutError:
            raise HTTPException(408, "本地朗读请求超时") from None
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
