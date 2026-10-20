import asyncio
import io
import json
import sys
import threading
import wave
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
import server
from fastapi import HTTPException, Request


def worker_with_model():
    worker = server.Synthesizer()
    worker.model = SimpleNamespace(tokenizer=SimpleNamespace(vocab={"a": 1}), create=lambda *args, **kwargs: (np.ones(240, dtype=np.float32) * 0.1, 24000))
    worker.g2p = {language: lambda text: ("a" * len(text), None) for language in ("ja", "zh-cn")}
    worker.load = lambda: None
    return worker


def request(data=b'{"text":"hello","language":"ja"}'):
    async def receive():
        return {"type": "http.request", "body": data, "more_body": False}

    return Request({"type": "http", "headers": [(b"content-type", b"application/json")]}, receive)


@pytest.mark.parametrize("language,voice", [("ja", "jf_alpha"), ("zh-cn", "zf_xiaobei")])
async def test_synthesis_uses_fixed_voice_phonemes_and_pcm_wav(language, voice):
    worker = worker_with_model()
    seen = []

    def create(text, **kwargs):
        seen.append((text, kwargs))
        return np.array([-2, 0, 2], dtype=np.float32), 24000

    worker.model.create = create
    app = server.create_app(worker)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://tts") as client,
    ):
        assert (await client.get("/health")).json() == {"ready": True}
        response = await client.post("/synthesize", json={"text": "你好", "language": language})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(response.content)) as audio:
        assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth(), audio.getnframes()) == (24000, 1, 2, 3)
    assert seen == [("aa", {"voice": voice, "is_phonemes": True})]


@pytest.mark.parametrize("body", [
    {}, {"text": "hi", "language": "en"}, {"text": "hi", "language": "ja", "voice": "injected"},
    {"text": 1, "language": "ja"}, {"text": "", "language": "ja"},
    {"text": "x" * 301, "language": "ja"}, {"text": "x\x00", "language": "ja"},
    {"text": "\ud800", "language": "ja"}, ["hi", "ja"],
])
def test_strict_schema_and_bounds(body):
    with pytest.raises(HTTPException) as error:
        server.parse_body(json.dumps(body).encode())
    assert error.value.status_code == 422
    assert server.parse_body(json.dumps({"text": "你" * 300, "language": "zh-cn"}).encode())[0] == "你" * 300


async def test_request_stream_size_mime_and_lock_release():
    worker = worker_with_model()
    app = server.create_app(worker)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://tts") as client,
    ):
        assert (await client.post("/synthesize", content=b"x", headers={"Content-Type": "text/plain"})).status_code == 415
        assert (await client.post("/synthesize", content=b"x" * 4097, headers={"Content-Type": "application/json"})).status_code == 413
        assert (await client.post("/synthesize", content=b"\xff", headers={"Content-Type": "application/json"})).status_code == 422
        assert not worker.lock.locked()


@pytest.mark.parametrize("audio,rate,status", [
    (np.array([], dtype=np.float32), 24000, 503),
    (np.array([np.nan]), 24000, 503),
    (np.array([np.inf]), 24000, 503),
    (np.ones((2, 2)), 24000, 503),
    (np.ones(2), 16000, 503),
    (np.ones(server.MAX_SAMPLES + 1), 24000, 422),
], ids=["empty", "nan", "infinite", "stereo", "rate", "too-long"])
def test_output_validation_and_real_worker_lock_release(audio, rate, status):
    worker = worker_with_model()
    worker.model.create = lambda *args, **kwargs: (audio, rate)
    worker.lock.acquire()
    with pytest.raises(HTTPException) as error:
        worker.synthesize("你好", "zh-cn")
    assert error.value.status_code == status
    assert not worker.lock.locked()


def test_phonemes_and_chunks_are_bounded_before_native_call():
    worker = worker_with_model()
    worker.g2p["ja"] = lambda text: ("a" * 2401, None)
    worker.lock.acquire()
    with pytest.raises(HTTPException) as error:
        worker.synthesize("test", "ja")
    assert error.value.status_code == 422
    assert not worker.lock.locked()
    seen = []
    worker.g2p["ja"] = lambda text: ("a" * 500, None)
    worker.model.create = lambda text, **kwargs: (seen.append(len(text)) or np.ones(1), 24000)
    worker.lock.acquire()
    worker.synthesize("test", "ja")
    assert seen == [400, 100]


async def test_cancel_keeps_actual_worker_locked_and_health_responsive():
    worker = worker_with_model()
    started, finish, finished = threading.Event(), threading.Event(), threading.Event()

    def slow(*args, **kwargs):
        started.set()
        try:
            finish.wait(timeout=3)
            return np.ones(24), 24000
        finally:
            finished.set()

    worker.model.create = slow
    app = server.create_app(worker)
    async with app.router.lifespan_context(app):
        endpoint = next(route.endpoint for route in app.routes if route.path == "/synthesize")
        task = asyncio.create_task(endpoint(request()))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert worker.lock.locked()
            with pytest.raises(HTTPException) as error:
                await endpoint(request())
            assert error.value.status_code == 429
            health = next(route.endpoint for route in app.routes if route.path == "/health")
            assert await asyncio.wait_for(health(), 0.1) == {"ready": True}
        finally:
            finish.set()
            assert await asyncio.to_thread(finished.wait, 1)


async def test_unready_is_explicit():
    app = server.create_app(server.Synthesizer())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://tts") as client:
        assert (await client.get("/health")).status_code == 503
        assert (await client.post("/synthesize", json={"text": "你好", "language": "zh-cn"})).status_code == 503


def test_missing_files_fail_before_any_g2p_or_model_import(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "MODEL_PATH", tmp_path / "model.onnx")
    monkeypatch.setattr(server, "VOICES_PATH", tmp_path / "voices.bin")
    monkeypatch.setitem(sys.modules, "unidic_lite", SimpleNamespace(DICDIR=str(tmp_path / "dict")))
    with pytest.raises(RuntimeError, match="不完整"):
        server.Synthesizer().load()
    for path in (server.MODEL_PATH, server.VOICES_PATH):
        path.write_bytes(b"test")
    (tmp_path / "dict").mkdir()
    for name in server.DICT_FILES[:-1]:
        (tmp_path / "dict" / name).write_bytes(b"test")
    with pytest.raises(RuntimeError, match="不完整"):
        server.local_assets()
    (tmp_path / "dict" / server.DICT_FILES[-1]).write_bytes(b"test")
    assert server.local_assets() == tmp_path / "dict"


def test_errors_never_expose_text_or_phonemes():
    worker = worker_with_model()

    def fail(*args, **kwargs):
        raise RuntimeError("/private/model user text secret phonemes")

    worker.model.create = fail
    worker.lock.acquire()
    with pytest.raises(HTTPException) as error:
        worker.synthesize("你好", "zh-cn")
    assert error.value.status_code == 503
    assert error.value.detail == "本地朗读服务暂时不可用"


@pytest.mark.parametrize("language", ["ja", "zh-cn"])
def test_all_phonemes_must_be_in_model_vocab_before_inference(language):
    worker = worker_with_model()
    worker.g2p[language] = lambda text: ("aƫ", None)
    worker.model.create = lambda *args, **kwargs: pytest.fail("unknown phonemes must never reach inference")
    worker.lock.acquire()
    with pytest.raises(HTTPException) as error:
        worker.synthesize("test", language)
    assert error.value.status_code == 422
    assert "ƫ" not in error.value.detail
    assert not worker.lock.locked()


def test_whole_reply_g2p_is_once_before_phoneme_windowing():
    text = "あ" * 59 + "今日も一緒に練習しよう。"
    seen = []

    def converter(value):
        seen.append(value)
        return "a" * 801, None

    assert list(map(len, server.phoneme_chunks(converter, text, {"a": 1}))) == [400, 400, 1]
    assert seen == [text]


@pytest.mark.parametrize("data", [
    b'{"text":"hi","text":"other","language":"ja"}',
    b"[" * 2000 + b"]" * 2000,
])
def test_duplicate_fields_and_nested_json_fail_safely(data):
    with pytest.raises(HTTPException) as error:
        server.parse_body(data)
    assert error.value.status_code == 422


async def test_slow_request_body_times_out_and_releases_admission_lock(monkeypatch):
    original_timeout = asyncio.timeout
    monkeypatch.setattr(server.asyncio, "timeout", lambda seconds: original_timeout(0.01))
    worker = worker_with_model()
    app = server.create_app(worker)

    async def receive():
        await asyncio.Event().wait()

    slow_request = Request({"type": "http", "headers": [(b"content-type", b"application/json")]}, receive)
    async with app.router.lifespan_context(app):
        endpoint = next(route.endpoint for route in app.routes if route.path == "/synthesize")
        with pytest.raises(HTTPException) as error:
            await endpoint(slow_request)
        assert error.value.status_code == 408
        assert not worker.lock.locked()


def test_startup_warmup_uses_the_same_strict_vocabulary_check(monkeypatch):
    monkeypatch.setattr(server, "local_assets", lambda: None)
    monkeypatch.setitem(sys.modules, "jieba", SimpleNamespace(setLogLevel=lambda level: None, dt=SimpleNamespace()))
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(
        SessionOptions=SimpleNamespace, InferenceSession=lambda *args, **kwargs: None,
    ))
    model = SimpleNamespace(tokenizer=SimpleNamespace(vocab={"a": 1}))
    model.create = lambda *args, **kwargs: pytest.fail("unsupported warmup phonemes must stop startup")
    monkeypatch.setitem(sys.modules, "kokoro_onnx", SimpleNamespace(Kokoro=SimpleNamespace(from_session=lambda *args: model)))
    monkeypatch.setitem(sys.modules, "misaki", SimpleNamespace(zh=SimpleNamespace(ZHG2P=lambda: lambda text: ("a", None))))
    monkeypatch.setitem(sys.modules, "misaki.cutlet", SimpleNamespace(Cutlet=lambda: lambda text: ("ƫ", None)))
    worker = server.Synthesizer()
    with pytest.raises(HTTPException) as error:
        worker.load()
    assert error.value.status_code == 422
    assert worker.model is None
