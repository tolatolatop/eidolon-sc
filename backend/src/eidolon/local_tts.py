"""Bounded, private access to the administrator-selected offline Kokoro sidecar."""

import asyncio
import json
import struct
from typing import Literal

import httpx
from fastapi import HTTPException

MAX_TEXT_CHARACTERS = 300
MAX_TEXT_BYTES = 1200
MAX_AUDIO_BYTES = 44 + 60 * 24000 * 2


def validate_wav(data: bytes) -> bytes:
    """Require the sidecar's canonical PCM16, mono, 24kHz RIFF/WAV container."""
    if not 44 < len(data) <= MAX_AUDIO_BYTES:
        raise ValueError("invalid WAV length")
    riff, size, wave, fmt, fmt_size, codec, channels, rate, byte_rate, align, bits, tag, count = struct.unpack("<4sI4s4sIHHIIHH4sI", data[:44])
    if (riff != b"RIFF" or wave != b"WAVE" or fmt != b"fmt " or tag != b"data"
            or size != len(data) - 8 or count != len(data) - 44 or count % 2
            or (fmt_size, codec, channels, rate, byte_rate, align, bits) != (16, 1, 1, 24000, 48000, 2, 16)):
        raise ValueError("invalid PCM WAV")
    return data


async def _request(url: str, *, text: str | None = None,
                   language: Literal["ja", "zh-cn"] = "ja") -> bytes:
    """Never forward cookies, credentials, environment proxies or upstream errors."""
    synthesizing = text is not None
    try:
        async with asyncio.timeout(100 if synthesizing else 3):
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
                async with client.stream(
                    "POST" if synthesizing else "GET",
                    url.rstrip("/") + ("/synthesize" if synthesizing else "/health"),
                    json={"text": text, "language": language} if synthesizing else None,
                    headers={"Accept-Encoding": "identity"},
                    timeout=httpx.Timeout(95 if synthesizing else 2, connect=2),
                ) as response:
                    if synthesizing and response.status_code == 429:
                        raise HTTPException(429, "本地朗读正在处理，请稍后再试", headers={"Retry-After": "3"})
                    if synthesizing and response.status_code in {413, 422}:
                        raise HTTPException(422, "回复过长或没有可合成的语音，请选择较短回复")
                    mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if (response.status_code != 200
                            or response.headers.get("content-encoding", "identity") != "identity"
                            or mime != ("audio/wav" if synthesizing else "application/json")):
                        raise ValueError("invalid sidecar response")
                    maximum = MAX_AUDIO_BYTES if synthesizing else 1024
                    body = bytearray()
                    async for chunk in response.aiter_raw():
                        if len(body) + len(chunk) > maximum:
                            raise ValueError("oversized response")
                        body.extend(chunk)
                    return bytes(body)
    except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError, TypeError):
        raise HTTPException(503, "本地朗读服务暂时不可用，请稍后重试") from None


async def ready(url: str) -> bool:
    try:
        status = json.loads(await _request(url))
        return isinstance(status, dict) and status.get("ready") is True
    except (HTTPException, ValueError, UnicodeError):
        return False


async def synthesize(url: str, text: str, *, language: Literal["ja", "zh-cn"]) -> bytes:
    data = await _request(url, text=text, language=language)
    try:
        return validate_wav(data)
    except (ValueError, struct.error):
        raise HTTPException(503, "本地朗读服务返回了无效音频，请重试") from None
