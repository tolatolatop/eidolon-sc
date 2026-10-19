"""Private reply read-aloud through Volcengine's V3 HTTP Chunked API.

Protocol: https://docs.volcengine.com/docs/DoubaoVoice/HTTPChunkedSSEUnidirectionalStreaming-V3
No provider response text, credentials or conversation text belongs in errors/logs.
"""

import asyncio
import base64
import binascii
import json
import uuid
from typing import Literal

import httpx

from eidolon.config import Settings

URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
MAX_TEXT_CHARACTERS = 2000
MAX_TEXT_BYTES = 6000
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
MAX_AUDIO_BYTES = 8 * 1024 * 1024
TIMEOUT_SECONDS = 35


class SynthesisFailed(Exception):
    """A bounded, generic failure safe to show to the browser."""


def configured(settings: Settings) -> bool:
    return bool(
        settings.volcengine_tts_api_key
        and settings.volcengine_tts_speaker
        and settings.volcengine_tts_resource_id
    )


async def synthesize(
    settings: Settings, text: str, *, language: Literal["ja", "zh-cn"] = "ja",
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes:
    """Assemble MP3 only after an explicit successful completion frame.

    Bound the full wire response (including unterminated lines) and decoded audio.
    aiter_bytes handles HTTP chunk framing; our buffer handles split JSON lines.
    """
    audio = bytearray()
    pending = bytearray()
    total = 0
    finished = False

    def frame(line: bytes) -> None:
        nonlocal finished
        if not line.strip():
            return
        if finished:
            raise SynthesisFailed("语音服务返回无效数据，请稍后重试")
        try:
            data = json.loads(line)
            if not isinstance(data, dict) or type(data.get("code")) is not int:
                raise ValueError
            if data["code"] not in (0, 20000000):
                raise SynthesisFailed("语音合成失败，请检查音色授权或稍后重试")
            encoded = data.get("data")
            if encoded is not None and encoded != "":
                if not isinstance(encoded, str):
                    raise ValueError
                audio.extend(base64.b64decode(encoded, validate=True))
            if len(audio) > MAX_AUDIO_BYTES:
                raise SynthesisFailed("语音服务返回内容过大")
            finished = data["code"] == 20000000
        except (ValueError, UnicodeError, binascii.Error) as error:
            raise SynthesisFailed("语音服务返回无效数据，请稍后重试") from error

    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15, connect=5), transport=transport,
                follow_redirects=False,
            ) as client:
                async with client.stream(
                    "POST", URL,
                    headers={
                        "X-Api-Key": settings.volcengine_tts_api_key or "",
                        "X-Api-Resource-Id": settings.volcengine_tts_resource_id,
                        "X-Api-Request-Id": str(uuid.uuid4()),
                    },
                    json={"req_params": {
                        "text": text,
                        "speaker": settings.volcengine_tts_speaker,
                        "audio_params": {"format": "mp3", "sample_rate": 24000},
                        "additions": json.dumps({"explicit_language": language}),
                    }},
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_RESPONSE_BYTES:
                            raise SynthesisFailed("语音服务返回内容过大")
                        pending.extend(chunk)
                        while (end := pending.find(b"\n")) >= 0:
                            frame(bytes(pending[:end]))
                            del pending[:end + 1]
                    if pending:
                        frame(bytes(pending))
    except (httpx.HTTPError, TimeoutError) as error:
        raise SynthesisFailed("语音服务暂时不可用，请稍后重试") from error
    if not finished or not audio:
        raise SynthesisFailed("语音未完整生成，请稍后重试")
    return bytes(audio)
