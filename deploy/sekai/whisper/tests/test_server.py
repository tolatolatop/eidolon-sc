import asyncio
import io
import threading
import wave
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
from fastapi import HTTPException, Request

import server


def wav(seconds: float = 1) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * int(seconds * 16000))
    return output.getvalue()


def worker_with_model(text="你好"):
    worker = server.Transcriber()

    def transcribe(audio, **kwargs):
        assert isinstance(audio, np.ndarray)
        assert kwargs["vad_filter"] is True
        assert kwargs["condition_on_previous_text"] is False
        return [SimpleNamespace(text=text)] if text else [], SimpleNamespace(language="zh")

    worker.model = SimpleNamespace(transcribe=transcribe)
    worker.load = lambda: None
    return worker


def request(data: bytes) -> Request:
    async def receive():
        return {"type": "http.request", "body": data, "more_body": False}

    return Request({"type": "http", "headers": [(b"content-type", b"audio/wav")]}, receive)


def test_bounded_decode_rejects_long_and_damaged_audio():
    assert server.decode_bounded(wav()).shape == (16000,)
    assert server.decode_bounded(wav(30)).shape == (480000,)
    for data in (wav(30.01), b"not-audio", b"#EXTM3U\nhttp://localhost/secret"):
        with pytest.raises(HTTPException) as error:
            server.decode_bounded(data)
        assert error.value.status_code == 422


def test_sample_bound_cannot_be_bypassed_by_absent_container_duration(monkeypatch):
    original = server.MAX_SAMPLES
    monkeypatch.setattr(server, "MAX_SAMPLES", 8000)
    with pytest.raises(HTTPException) as error:
        server.decode_bounded(wav(1))
    assert error.value.status_code == 422
    assert original == 30 * 16000


def test_decoder_deadline(monkeypatch):
    now = iter([0.0, 11.0])
    monkeypatch.setattr(server.time, "monotonic", lambda: next(now))
    with pytest.raises(HTTPException) as error:
        server.decode_bounded(wav(1))
    assert error.value.status_code == 422
    assert "超时" in error.value.detail


@pytest.mark.parametrize("text", ["你好", ""])
async def test_mocked_model_transcription_and_silence(text):
    app = server.create_app(worker_with_model(text))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://sidecar") as client:
            assert (await client.get("/health")).json() == {"ready": True}
            response = await client.post("/transcribe?language=zh", content=wav(), headers={"Content-Type": "audio/wav"})
            assert response.status_code == 200
            assert response.json() == {"text": text, "language": "zh"}
            assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("body,mime,language,status", [
    (b"", "audio/mp4", "auto", 422),
    (b"x", "text/html", "auto", 415),
    (b"x", "audio/mp4", "en", 422),
    (b"x" * (server.MAX_BYTES + 1), "audio/webm", "auto", 413),
    (b"broken", "audio/mp4", "auto", 422),
    (wav(31), "audio/wav", "auto", 422),
])
async def test_invalid_inputs(body, mime, language, status):
    app = server.create_app(worker_with_model())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://sidecar") as client:
            response = await client.post(f"/transcribe?language={language}", content=body, headers={"Content-Type": mime})
            assert response.status_code == status


async def test_output_bound_and_safe_error():
    worker = worker_with_model("x" * 4001)
    app = server.create_app(worker)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://sidecar") as client:
            assert (await client.post("/transcribe", content=wav(), headers={"Content-Type": "audio/wav"})).status_code == 422
            def fail(*args, **kwargs):
                raise RuntimeError("/private/path secret")
            worker.model.transcribe = fail
            response = await client.post("/transcribe", content=wav(), headers={"Content-Type": "audio/wav"})
            assert response.status_code == 503
            assert "private" not in response.text


async def test_cancelling_request_keeps_real_worker_locked_and_event_loop_free():
    worker = worker_with_model()
    started, finish, finished = threading.Event(), threading.Event(), threading.Event()

    def slow(*args, **kwargs):
        started.set()
        try:
            finish.wait(timeout=3)
            return [], SimpleNamespace(language="zh")
        finally:
            finished.set()

    worker.model.transcribe = slow
    app = server.create_app(worker)
    async with app.router.lifespan_context(app):
        endpoint = next(route.endpoint for route in app.routes if route.path == "/transcribe")
        task = asyncio.create_task(endpoint(request(wav()), language="auto"))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert worker.lock.locked()
            with pytest.raises(HTTPException) as error:
                await endpoint(request(wav()), language="auto")
            assert error.value.status_code == 429
            health = next(route.endpoint for route in app.routes if route.path == "/health")
            assert await asyncio.wait_for(health(), timeout=0.1) == {"ready": True}
        finally:
            finish.set()
            assert await asyncio.to_thread(finished.wait, 1)


async def test_health_not_ready_until_model_loaded():
    app = server.create_app(server.Transcriber())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://sidecar") as client:
        assert (await client.get("/health")).status_code == 503


def test_model_loading_is_offline_cpu_int8_four_threads(monkeypatch):
    seen = []
    monkeypatch.setattr(server, "WhisperModel", lambda *args, **kwargs: seen.append((args, kwargs)))
    monkeypatch.setenv("WHISPER_MODEL_PATH", "/mounted/small")
    server.Transcriber().load()
    assert seen == [(("/mounted/small",), {"device": "cpu", "compute_type": "int8", "cpu_threads": 4, "num_workers": 1, "local_files_only": True})]
