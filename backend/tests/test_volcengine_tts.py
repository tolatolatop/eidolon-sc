import asyncio
import base64
import json
from dataclasses import replace

import httpx
import pytest

from eidolon import volcengine_tts as tts
from eidolon.config import Settings


def frames(*items: dict) -> bytes:
    return b"\n".join(json.dumps(item).encode() for item in items)


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


@pytest.fixture
def voice_settings(settings: Settings) -> Settings:
    return replace(settings, volcengine_tts_api_key="fake-volc-key",
                   volcengine_tts_speaker="test-authorized-speaker")


@pytest.mark.parametrize("text,language", [("こんにちは", "ja"), ("你好", "zh-cn")])
async def test_new_console_protocol_joins_split_lines_and_final_audio(voice_settings, text, language):
    raw = frames(
        {"code": 0, "data": base64.b64encode(b"mp3-part-one").decode()},
        {"code": 0, "data": None, "sentence": {"text": "ignored"}},
        {"code": 20000000, "data": base64.b64encode(b"-part-two").decode()},
    )
    stream = Chunks([raw[:7], raw[7:31], raw[31:]])

    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == tts.URL
        assert request.method == "POST"
        assert request.headers["X-Api-Key"] == "fake-volc-key"
        assert request.headers["X-Api-Resource-Id"] == "seed-tts-2.0"
        assert request.headers["X-Api-Request-Id"]
        params = json.loads(request.content)["req_params"]
        assert params["text"] == text
        assert params["speaker"] == "test-authorized-speaker"
        assert params["audio_params"]["format"] == "mp3"
        assert json.loads(params["additions"]) == {"explicit_language": language}
        return httpx.Response(200, stream=stream)

    audio = await tts.synthesize(voice_settings, text, language=language, transport=httpx.MockTransport(handle))
    assert audio == b"mp3-part-one-part-two"
    assert stream.closed


@pytest.mark.parametrize("raw", [
    frames({"code": 45000000, "message": "sensitive provider message"}),
    frames({"code": 0, "data": "bXAz"}),  # no completion
    frames({"code": 0, "data": "%%%"}, {"code": 20000000}),
    frames({"code": 20000000, "data": None}),  # no audio
    b"not JSON", b"[]", b'{"code":false}',
    frames({"code": 20000000, "data": "bXAz"}, {"code": 0, "data": "bXAz"}),
])
async def test_rejects_provider_failure_and_incomplete_or_malformed_audio(voice_settings, raw):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=raw))
    with pytest.raises(tts.SynthesisFailed) as error:
        await tts.synthesize(voice_settings, "text", transport=transport)
    assert "sensitive" not in str(error.value)
    assert "fake-volc-key" not in str(error.value)


@pytest.mark.parametrize("limit", ["MAX_RESPONSE_BYTES", "MAX_AUDIO_BYTES"])
async def test_response_limits_also_cover_unterminated_lines(voice_settings, monkeypatch, limit):
    monkeypatch.setattr(tts, limit, 4)
    raw = frames({"code": 20000000, "data": base64.b64encode(b"too large").decode()})
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=raw))
    with pytest.raises(tts.SynthesisFailed, match="过大"):
        await tts.synthesize(voice_settings, "text", transport=transport)


async def test_http_failure_never_exposes_body_or_key(voice_settings):
    transport = httpx.MockTransport(lambda _: httpx.Response(403, text="fake-volc-key"))
    with pytest.raises(tts.SynthesisFailed, match="暂时不可用") as error:
        await tts.synthesize(voice_settings, "text", transport=transport)
    assert "fake-volc-key" not in str(error.value)


async def test_total_timeout_closes_stream(voice_settings, monkeypatch):
    monkeypatch.setattr(tts, "TIMEOUT_SECONDS", 0.01)

    class Stalled(Chunks):
        async def __aiter__(self):
            yield b""
            await asyncio.Event().wait()

    stream = Stalled([])
    transport = httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))
    with pytest.raises(tts.SynthesisFailed, match="暂时不可用"):
        await tts.synthesize(voice_settings, "text", transport=transport)
    assert stream.closed


def test_private_env_loads_and_hides_key(monkeypatch):
    monkeypatch.setenv("CHAT_LLM_BASE_URL", "http://llm.invalid/v1")
    monkeypatch.setenv("CHAT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("CHAT_LLM_MODEL", "test")
    monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", "never-print-this-test-key")
    monkeypatch.setenv("VOLCENGINE_TTS_SPEAKER", "authorized-id")
    monkeypatch.delenv("VOLCENGINE_TTS_RESOURCE_ID", raising=False)
    settings = Settings.from_env()
    assert settings.volcengine_tts_api_key == "never-print-this-test-key"
    assert settings.volcengine_tts_resource_id == "seed-tts-2.0"
    assert "never-print-this-test-key" not in repr(settings)
    assert tts.configured(settings)
    assert not tts.configured(replace(settings, volcengine_tts_speaker=None))
