import io
import json
import struct
import wave
from dataclasses import replace

import httpx
import pytest
from fastapi import HTTPException

from eidolon import local_tts
from tests.test_read_aloud_api import private_hash, private_settings  # noqa: F401


def wav():
    result = io.BytesIO()
    with wave.open(result, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\x00\x00" * 24)
    return result.getvalue()


@pytest.mark.parametrize("url", ["file:///tmp/tts", "http://u:p@tts", "http://tts/path", "http://tts?query", "http://tts#fragment", "http://tts:0", "http://tts:bad"])
def test_url_rejects_credentials_paths_queries_and_non_http(settings, url):
    with pytest.raises(RuntimeError, match="EIDOLON_LOCAL_TTS_URL"):
        replace(settings, local_tts_url=url)


@pytest.mark.parametrize("url", ["http://tts:8000", "https://tts/", "http://[::1]:8000"])
def test_local_service_url_allowed(settings, url):
    assert replace(settings, local_tts_url=url).local_tts_url == url


@pytest.mark.parametrize("change", ["short", "stereo", "rate", "float", "length", "empty", "trailing"])
def test_wav_validation_is_strict(change):
    data = bytearray(wav())
    if change == "short":
        data = data[:30]
    elif change == "stereo":
        struct.pack_into("<H", data, 22, 2)
    elif change == "rate":
        struct.pack_into("<I", data, 24, 16000)
    elif change == "float":
        struct.pack_into("<H", data, 20, 3)
    elif change == "length":
        struct.pack_into("<I", data, 40, 999)
    elif change == "empty":
        data = data[:44]
    elif change == "trailing":
        data += b"extra"
    with pytest.raises(ValueError):
        local_tts.validate_wav(bytes(data))


def mock_client(monkeypatch, handler):
    original = httpx.AsyncClient

    def client(**kwargs):
        assert kwargs == {"trust_env": False, "follow_redirects": False}
        return original(transport=httpx.MockTransport(handler), **kwargs)

    class Stream(httpx.AsyncByteStream):
        def __init__(self, data):
            self.data = data

        async def __aiter__(self):
            for start in range(0, len(self.data), 16384):
                yield self.data[start:start + 16384]

    original_handler = handler

    def streamed(request):
        response = original_handler(request)
        return httpx.Response(response.status_code, headers=response.headers, stream=Stream(response.content))

    handler = streamed
    monkeypatch.setattr(local_tts.httpx, "AsyncClient", client)


async def test_health_and_synthesis_use_bounded_local_protocol(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"ready": True})
        assert json.loads(request.content) == {"text": "你好", "language": "zh-cn"}
        return httpx.Response(200, headers={"content-type": "audio/wav"}, content=wav())

    mock_client(monkeypatch, handler)
    assert await local_tts.ready("http://tts:8000")
    assert await local_tts.synthesize("http://tts:8000", "你好", language="zh-cn") == wav()
    assert [request.url.path for request in seen] == ["/health", "/synthesize"]
    assert all("cookie" not in request.headers for request in seen)


@pytest.mark.parametrize("status,mime,data,expected", [
    (429, "text/html", b"secret", 429),
    (422, "application/json", b"secret", 422),
    (500, "text/html", b"secret", 503),
    (200, "audio/mpeg", b"secret", 503),
    (200, "audio/wav", b"secret", 503),
    (200, "audio/wav", b"x" * (local_tts.MAX_AUDIO_BYTES + 1), 503),
], ids=["busy", "bad-input", "upstream", "mime", "invalid-wav", "oversize"])
async def test_safe_failure_response(monkeypatch, status, mime, data, expected):
    mock_client(monkeypatch, lambda request: httpx.Response(status, headers={"content-type": mime}, content=data))
    with pytest.raises(HTTPException) as error:
        await local_tts.synthesize("http://tts", "你好", language="zh-cn")
    assert error.value.status_code == expected
    assert "secret" not in str(error.value.detail)


@pytest.mark.parametrize("body", [{"ready": False}, {"ready": "true"}, [], {"ready": True, "padding": "x" * 2000}])
async def test_health_is_truthful_and_bounded(monkeypatch, body):
    mock_client(monkeypatch, lambda request: httpx.Response(200, json=body))
    assert not await local_tts.ready("http://tts")
