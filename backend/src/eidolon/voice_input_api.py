"""Authenticated, memory-only access to the deployer's offline Whisper sidecar."""

import asyncio
import json
import re
import time
from contextlib import contextmanager, suppress
from typing import Iterator, Literal

import httpx
from fastapi import FastAPI, HTTPException, Request, Response

from eidolon.assembly import Backend
from eidolon.read_aloud_api import _until_disconnected
from eidolon.sessions import UserId

MAX_AUDIO_BYTES = 5 * 1024 * 1024
MAX_RESPONSE_BYTES = 20000
MAX_TEXT = 4000
MIME_TYPES = {"audio/webm", "audio/mp4", "audio/wav", "audio/x-wav", "audio/ogg", "audio/mpeg", "audio/flac"}


class VoiceInputLimiter:
    """Single private-deployment request, with a per-user three-second cooldown."""

    def __init__(self) -> None:
        self.active = False
        self.until: dict[str, float] = {}

    @contextmanager
    def hold(self, user_id: str) -> Iterator[None]:
        now = time.monotonic()
        self.until = {key: at for key, at in self.until.items() if at > now}
        if self.active or user_id in self.until:
            raise HTTPException(429, "语音输入正在处理，请稍后再试", headers={"Retry-After": "3"})
        self.active = True
        try:
            yield
        finally:
            self.active = False
            self.until[user_id] = time.monotonic() + 3


async def _sidecar(url: str, path: str, *, data: bytes | None = None,
                   content_type: str = "", language: str = "auto") -> dict:
    """Do not forward cookies, own keys, environment proxies or upstream error bodies."""
    try:
        async with asyncio.timeout(120 if data is not None else 3):
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
                async with client.stream(
                    "POST" if data is not None else "GET", url.rstrip("/") + path,
                    params={"language": language} if data is not None else None,
                    content=data, headers={"Content-Type": content_type, "Accept-Encoding": "identity"},
                    timeout=httpx.Timeout(115 if data is not None else 2, connect=2),
                ) as response:
                    if response.status_code == 429:
                        raise HTTPException(429, "语音输入正在处理，请稍后再试", headers={"Retry-After": "3"})
                    if response.status_code == 413:
                        raise HTTPException(413, "录音不能超过5MiB")
                    if response.status_code in {415, 422}:
                        raise HTTPException(422, "录音损坏、格式不支持或超过30秒，请重新录音")
                    if response.status_code != 200:
                        raise ValueError("upstream unavailable")
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise ValueError("encoded response")
                    body = bytearray()
                    async for chunk in response.aiter_raw():
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ValueError("oversized response")
                        body.extend(chunk)
                    result = json.loads(body)
                    if not isinstance(result, dict):
                        raise ValueError("invalid response")
                    return result
    except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError, TypeError):
        raise HTTPException(503, "本地语音输入服务暂时不可用，请稍后重试") from None


async def _transcribe_connected(request: Request, url: str, data: bytes,
                                mime: str, language: str) -> dict:
    upstream = asyncio.create_task(_sidecar(
        url, "/transcribe", data=data, content_type=mime, language=language,
    ))
    disconnected = asyncio.create_task(_until_disconnected(request))
    try:
        await asyncio.wait({upstream, disconnected}, return_when=asyncio.FIRST_COMPLETED)
        if disconnected.done():
            raise HTTPException(499, "语音输入已取消")
        return await upstream
    finally:
        for task in (upstream, disconnected):
            task.cancel()
        for task in (upstream, disconnected):
            with suppress(asyncio.CancelledError):
                await task


def add_voice_input_routes(app: FastAPI, backend: Backend) -> None:
    settings = backend.settings
    limiter = VoiceInputLimiter()

    def private_url() -> str | None:
        if settings.private_password_hash is None:
            raise HTTPException(404, "没有此功能")
        return settings.local_whisper_url

    @app.get("/api/voice-input")
    async def availability(user_id: UserId, response: Response) -> dict:
        url = private_url()
        response.headers["Cache-Control"] = "no-store"
        if not url:
            return {"available": False, "reason": "unconfigured"}
        try:
            status = await _sidecar(url, "/health")
        except HTTPException:
            return {"available": False, "reason": "unready"}
        return {"available": status.get("ready") is True, "reason": "ready" if status.get("ready") is True else "unready"}

    @app.post("/api/voice-input/transcribe")
    async def transcribe(
        request: Request, response: Response, user_id: UserId,
        language: Literal["auto", "zh", "ja"] = "auto",
    ) -> dict:
        url = private_url()
        if not url:
            raise HTTPException(503, "本部署尚未配置本地语音输入")
        mime = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if mime not in MIME_TYPES:
            raise HTTPException(415, "音频格式不受支持")
        with limiter.hold(user_id):
            data = bytearray()
            try:
                async with asyncio.timeout(15):
                    async for chunk in request.stream():
                        if len(data) + len(chunk) > MAX_AUDIO_BYTES:
                            raise HTTPException(413, "录音不能超过5MiB")
                        data.extend(chunk)
            except TimeoutError:
                raise HTTPException(408, "录音上传超时，请重新录音") from None
            if not data:
                raise HTTPException(422, "录音为空")
            result = await _transcribe_connected(request, url, bytes(data), mime, language)
            text, detected = result.get("text"), result.get("language")
            if (not isinstance(text, str) or len(text) > MAX_TEXT
                    or len(text.encode()) > MAX_TEXT * 4 or not isinstance(detected, str)
                    or re.fullmatch(r"[a-z]{2,3}", detected) is None):
                raise HTTPException(503, "本地语音输入服务返回了无效结果，请重试")
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return {"text": text, "language": detected}
