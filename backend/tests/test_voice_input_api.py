import asyncio
from dataclasses import replace

import httpx
import pytest
from fastapi import HTTPException, Request

from eidolon import voice_input_api
from eidolon.sessions import SESSION_COOKIE
from tests.fakes import FakeLLM
from tests.test_read_aloud_api import private_hash, private_settings  # noqa: F401


@pytest.fixture
def configured(private_settings):
    return replace(private_settings, local_whisper_url="http://whisper:8000",
                   read_aloud_enabled=False)


@pytest.mark.parametrize("url", [
    "file:///private/model", "http://user:secret@whisper:8000",
    "http://whisper:badport", "http://whisper:8000/transcribe?secret=x",
])
def test_sidecar_address_is_administrator_config_without_credentials(settings, url):
    with pytest.raises(RuntimeError, match="EIDOLON_LOCAL_WHISPER_URL"):
        replace(settings, local_whisper_url=url)


async def test_private_auth_consent_and_origin(make_client, configured):
    public = make_client(FakeLLM([]))
    assert (await public.get("/api/voice-input")).status_code == 404
    assert (await public.post("/api/voice-input/transcribe")).status_code == 404
    client = make_client(FakeLLM([]), settings=configured)
    assert (await client.post("/api/voice-input/transcribe", headers={"Origin": "https://evil.invalid"})).status_code == 403
    client.cookies.delete(SESSION_COOKIE)
    assert (await client.get("/api/voice-input")).status_code == 401
    assert (await client.post("/api/voice-input/transcribe")).status_code == 401
    newcomer = make_client(FakeLLM([]), user=None, settings=configured)
    await newcomer.post("/api/auth/private-login", json={"password": "a-fake-test-password"})
    assert (await newcomer.get("/api/voice-input")).status_code == 428
    assert (await newcomer.post("/api/voice-input/transcribe")).status_code == 428


async def test_readiness_and_disabled_read_aloud(make_client, configured, monkeypatch):
    async def sidecar(*args, **kwargs):
        return {"ready": True}

    monkeypatch.setattr(voice_input_api, "_sidecar", sidecar)
    client = make_client(FakeLLM([]), settings=configured)
    response = await client.get("/api/voice-input")
    assert response.json() == {"available": True, "reason": "ready"}
    assert response.headers["cache-control"] == "no-store"
    assert (await client.get("/api/read-aloud")).json() == {"available": False, "enabled": False}
    assert (await client.post("/api/conversations/unknown/messages/1/read-aloud")).status_code == 404
    unconfigured = make_client(FakeLLM([]), settings=replace(configured, local_whisper_url=None))
    assert (await unconfigured.get("/api/voice-input")).json() == {"available": False, "reason": "unconfigured"}
    assert (await unconfigured.post("/api/voice-input/transcribe")).status_code == 503


async def test_transcribes_bytes_only_preserves_language_and_cooldown(make_client, configured, monkeypatch):
    seen = []

    async def sidecar(url, path, **kwargs):
        seen.append((url, path, kwargs))
        return {"text": "你好", "language": "zh"}

    monkeypatch.setattr(voice_input_api, "_sidecar", sidecar)
    client = make_client(FakeLLM([]), settings=configured)
    response = await client.post("/api/voice-input/transcribe?language=zh", content=b"fake-audio", headers={"Content-Type": "audio/webm;codecs=opus"})
    assert response.json() == {"text": "你好", "language": "zh"}
    assert response.headers["cache-control"] == "no-store"
    assert seen == [("http://whisper:8000", "/transcribe", {"data": b"fake-audio", "content_type": "audio/webm", "language": "zh"})]
    assert (await client.post("/api/voice-input/transcribe", content=b"audio", headers={"Content-Type": "audio/mp4"})).status_code == 429


@pytest.mark.parametrize("body,mime,language,expected", [
    (b"", "audio/mp4", "auto", 422),
    (b"x", "text/html", "auto", 415),
    (b"x", "audio/mp4", "en", 422),
    (b"x" * (voice_input_api.MAX_AUDIO_BYTES + 1), "audio/webm", "auto", 413),
])
async def test_rejects_invalid_input(make_client, configured, monkeypatch, body, mime, language, expected):
    async def never(*args, **kwargs):
        pytest.fail("invalid audio reached sidecar")

    monkeypatch.setattr(voice_input_api, "_sidecar", never)
    client = make_client(FakeLLM([]), settings=configured)
    response = await client.post(f"/api/voice-input/transcribe?language={language}", content=body, headers={"Content-Type": mime})
    assert response.status_code == expected


@pytest.mark.parametrize("result", [
    {"text": "x" * 4001, "language": "zh"},
    {"text": [], "language": "zh"}, {"text": "text", "language": "path/private"},
])
async def test_rejects_invalid_sidecar_results(make_client, configured, monkeypatch, result):
    async def sidecar(*args, **kwargs):
        return result

    monkeypatch.setattr(voice_input_api, "_sidecar", sidecar)
    client = make_client(FakeLLM([]), settings=configured)
    response = await client.post("/api/voice-input/transcribe", content=b"audio", headers={"Content-Type": "audio/wav"})
    assert response.status_code == 503
    assert "path/private" not in response.text


@pytest.mark.parametrize("status,body,expected", [
    (500, b"private-path-and-secret", 503),
    (200, b"x" * 20001, 503), (200, b"{broken", 503),
    (422, b"private decoder path", 422), (429, b"internal", 429),
], ids=["server-error", "oversized", "malformed-json", "bad-audio", "busy"])
async def test_sidecar_errors_and_response_bounds(monkeypatch, status, body, expected):
    original = httpx.AsyncClient

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield body

    def handler(request):
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        return httpx.Response(status, stream=Stream())

    monkeypatch.setattr(voice_input_api.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(HTTPException) as error:
        await voice_input_api._sidecar("http://whisper:8000", "/transcribe", data=b"audio")
    assert error.value.status_code == expected
    assert "private" not in str(error.value.detail)


async def test_global_concurrency_and_disconnect_cancels_proxy(monkeypatch):
    limiter = voice_input_api.VoiceInputLimiter()
    with limiter.hold("a"):
        with pytest.raises(HTTPException):
            with limiter.hold("b"):
                pass
    cancelled = asyncio.Event()

    async def sidecar(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def receive():
        return {"type": "http.disconnect"}

    monkeypatch.setattr(voice_input_api, "_sidecar", sidecar)
    with pytest.raises(HTTPException) as error:
        await voice_input_api._transcribe_connected(Request({"type": "http"}, receive), "http://whisper:8000", b"audio", "audio/wav", "auto")
    assert error.value.status_code == 499
    assert cancelled.is_set()
