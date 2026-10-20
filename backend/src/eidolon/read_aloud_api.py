"""Read a saved reply owned by the consenting user; never accept caller-supplied text."""

import asyncio
import math
import time
from collections.abc import Callable
from contextlib import contextmanager, suppress
from typing import Iterator, Literal

from fastapi import FastAPI, HTTPException, Request, Response

from eidolon import local_tts, volcengine_tts
from eidolon.assembly import Backend
from eidolon.delivery_cues import without_cues
from eidolon.sessions import UserId


class ReadAloudLimiter:
    """One in flight per user, then three seconds before another paid synthesis.

    State belongs to one app/process, not the database. Private deployment runs one
    worker; multiple workers need a shared limiter before exposing this endpoint.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._active: set[str] = set()
        self._until: dict[str, float] = {}

    @contextmanager
    def hold(self, user_id: str) -> Iterator[None]:
        now = self._clock()
        self._until = {key: at for key, at in self._until.items() if at > now}
        if user_id in self._active or user_id in self._until:
            wait = max(1, math.ceil(self._until.get(user_id, now + 3) - now))
            raise HTTPException(429, "朗读请求过于频繁，请稍后再试", headers={
                "Retry-After": str(wait),
            })
        self._active.add(user_id)
        try:
            yield
        finally:
            self._active.discard(user_id)
            self._until[user_id] = self._clock() + 3


async def _until_disconnected(request: Request) -> None:
    # The empty body has already been consumed. Wait on ASGI directly rather
    # than is_disconnected(), whose internal cancel scope can swallow the
    # cancellation of this watcher through BaseHTTPMiddleware.
    while (await request.receive())["type"] != "http.disconnect":
        pass


async def _audio(
    request: Request, backend: Backend, text: str, language: Literal["ja", "zh-cn"] = "ja",
) -> bytes:
    """Disconnect/stop aborts upstream instead of leaving a paid task behind."""
    synthesis = asyncio.create_task(
        local_tts.synthesize(backend.settings.local_tts_url, text, language=language)
        if backend.settings.local_tts_url else
        volcengine_tts.synthesize(backend.settings, text, language=language)
    )
    disconnected = asyncio.create_task(_until_disconnected(request))
    try:
        await asyncio.wait({synthesis, disconnected}, return_when=asyncio.FIRST_COMPLETED)
        if disconnected.done():
            raise HTTPException(499, "朗读已取消")
        return await synthesis
    finally:
        for task in (synthesis, disconnected):
            task.cancel()
        for task in (synthesis, disconnected):
            with suppress(asyncio.CancelledError):
                await task


def add_read_aloud_routes(app: FastAPI, backend: Backend) -> None:
    limiter = ReadAloudLimiter()
    settings, store = backend.settings, backend.store

    def private_only() -> None:
        if settings.private_password_hash is None:
            raise HTTPException(404, "没有此功能")

    @app.get("/api/read-aloud")
    async def availability(user_id: UserId, response: Response) -> dict:
        private_only()
        response.headers["Cache-Control"] = "no-store"
        if not settings.read_aloud_enabled:
            return {"available": False, "enabled": False}
        if settings.local_tts_url:
            ready = await local_tts.ready(settings.local_tts_url)
            return {
                "available": ready, "provider": "kokoro", "reason": "ready" if ready else "unready",
                "languages": ["ja", "zh-cn"], "voices": {"ja": "jf_alpha", "zh-cn": "zf_xiaobei"},
                "disclaimer": "本地合成音色，非官方角色声音",
            }
        return {"available": volcengine_tts.configured(settings)}

    @app.post("/api/conversations/{conversation_id}/messages/{message_id}/read-aloud")
    async def read_aloud(
        conversation_id: str, message_id: int, user_id: UserId, request: Request,
    ) -> Response:
        private_only()
        if not settings.read_aloud_enabled:
            raise HTTPException(404, "本部署未开启朗读")
        # Consume the empty request before monitoring disconnects. A body is never
        # useful here, and competing reads of an unconsumed body can stall middleware.
        async for chunk in request.stream():
            if chunk:
                raise HTTPException(422, "朗读请求只接受对话和消息 ID")
        message = store.owned_message(conversation_id, message_id, user_id)
        if message is None or message.role != "character":
            raise HTTPException(404, "没有可朗读的回复")
        language: Literal["ja", "zh-cn"] = "zh-cn"
        text = ""
        for candidate, candidate_language in ((message.ja, "ja"), (message.zh, "zh-cn"), (message.text, "zh-cn")):
            text = without_cues(candidate or "").strip()
            if text:
                language = "ja" if candidate_language == "ja" else "zh-cn"
                break
        if not text:
            raise HTTPException(422, "这条回复没有可朗读的文字")
        provider = local_tts if settings.local_tts_url else volcengine_tts
        if (len(text) > provider.MAX_TEXT_CHARACTERS
                or len(text.encode()) > provider.MAX_TEXT_BYTES):
            raise HTTPException(422, "这条回复过长，暂时不能朗读")
        if not settings.local_tts_url and not volcengine_tts.configured(settings):
            raise HTTPException(503, "朗读待配置：需要火山引擎密钥和已授权音色")
        with limiter.hold(user_id):
            try:
                audio = await _audio(request, backend, text, language)
            except volcengine_tts.SynthesisFailed as error:
                raise HTTPException(502, str(error)) from None
        return Response(audio, media_type="audio/wav" if settings.local_tts_url else "audio/mpeg", headers={
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        })
