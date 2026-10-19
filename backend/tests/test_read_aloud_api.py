import asyncio
import sqlite3
from dataclasses import replace

import pytest
from fastapi import HTTPException, Request

from eidolon import read_aloud_api, volcengine_tts
from eidolon.config import Settings
from eidolon.private_login import hash_password
from eidolon.reply_format import Segment
from eidolon.sessions import SESSION_COOKIE
from tests.conftest import ClientFactory
from tests.fakes import FakeLLM, build_faked


@pytest.fixture(scope="module")
def private_hash():
    return hash_password("a-fake-test-password")


@pytest.fixture
def private_settings(settings: Settings, private_hash) -> Settings:
    return replace(settings, dev_login=False, private_password_hash=private_hash,
                   volcengine_tts_api_key="fake-volc-key", volcengine_tts_speaker="test-speaker")


@pytest.fixture
def saved_reply(private_settings):
    backend = build_faked(private_settings, FakeLLM([]))
    user = backend.store.create_user("producer")
    backend.store.consent(user.id, backend.clock())
    conversation = backend.store.create_conversation(user.id, "mano")
    reply = backend.store.add_turn(conversation.id, "user words", [Segment("[happy] はい", "好的")])
    yield conversation, reply
    backend.store.close()


def path(conversation, message):
    return f"/api/conversations/{conversation.id}/messages/{message.id}/read-aloud"


async def test_reads_only_saved_reply_without_cues_and_never_caches(
    make_client: ClientFactory, private_settings, saved_reply, monkeypatch,
):
    conversation, reply = saved_reply
    seen = []

    async def synthesize(settings, text, *, language):
        seen.append((text, language))
        return b"mp3"

    monkeypatch.setattr(volcengine_tts, "synthesize", synthesize)
    client = make_client(FakeLLM([]), settings=private_settings)
    assert (await client.get("/api/read-aloud")).json() == {"available": True}
    injected = await client.post(path(conversation, reply), json={"text": "injected text"})
    assert injected.status_code == 422
    assert seen == []
    response = await client.post(path(conversation, reply))
    assert response.status_code == 200
    assert response.content == b"mp3"
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["cache-control"] == "no-store"
    assert seen == [("はい", "ja")]
    assert (await client.post(path(conversation, reply))).status_code == 429


async def test_rejects_foreign_owner_wrong_conversation_user_message_and_missing(
    make_client: ClientFactory, private_settings, saved_reply, monkeypatch,
):
    conversation, reply = saved_reply

    async def never(*args, **kwargs):
        pytest.fail("unauthorized synthesis")

    monkeypatch.setattr(volcengine_tts, "synthesize", never)
    owner = make_client(FakeLLM([]), settings=private_settings)
    stranger = make_client(FakeLLM([]), user="stranger", settings=private_settings)
    for client, url in [
        (stranger, path(conversation, reply)),
        (owner, path(conversation, replace(reply, id=reply.id - 1))),
        (owner, path(conversation, replace(reply, id=9999))),
        (owner, path(replace(conversation, id="unknown"), reply)),
    ]:
        assert (await client.post(url)).status_code == 404


async def test_auth_origin_and_consent_apply(make_client, private_settings, saved_reply):
    conversation, reply = saved_reply
    client = make_client(FakeLLM([]), settings=private_settings)
    assert (await client.post(path(conversation, reply), headers={"Origin": "https://evil.invalid"})).status_code == 403
    client.cookies.delete(SESSION_COOKIE)
    assert (await client.post(path(conversation, reply))).status_code == 401
    assert (await client.get("/api/read-aloud")).status_code == 401

    newcomer = make_client(FakeLLM([]), user=None, settings=private_settings)
    assert (await newcomer.post("/api/auth/private-login", json={"password": "a-fake-test-password"})).status_code == 204
    # Use a fresh DB in other tests; here private owner is newly made by the login.
    assert (await newcomer.post(path(conversation, reply))).status_code == 428
    assert (await newcomer.get("/api/read-aloud")).status_code == 428


async def test_unconfigured_is_explicit_and_normal_deployment_has_no_feature(
    make_client, private_settings, saved_reply,
):
    conversation, reply = saved_reply
    client = make_client(FakeLLM([]), settings=replace(private_settings, volcengine_tts_api_key=None))
    assert (await client.get("/api/read-aloud")).json() == {"available": False}
    assert (await client.post(path(conversation, reply))).status_code == 503
    normal = make_client(FakeLLM([]))
    assert (await normal.get("/api/read-aloud")).status_code == 404
    assert (await normal.post(path(conversation, reply))).status_code == 404


@pytest.mark.parametrize("text", ["[happy]", "あ" * 2001])
async def test_empty_and_excessive_saved_text_are_rejected(
    make_client, private_settings, saved_reply, text,
):
    conversation, _ = saved_reply
    backend = build_faked(private_settings, FakeLLM([]))
    message = backend.store.add_turn(conversation.id, "test", [Segment(text, "")])
    backend.store.close()
    client = make_client(FakeLLM([]), settings=private_settings)
    assert (await client.post(path(conversation, message))).status_code == 422


async def test_provider_failure_is_safe_and_rate_limited(make_client, private_settings, saved_reply, monkeypatch):
    conversation, reply = saved_reply

    async def fail(*args, **kwargs):
        raise volcengine_tts.SynthesisFailed("语音服务暂时不可用")

    monkeypatch.setattr(volcengine_tts, "synthesize", fail)
    client = make_client(FakeLLM([]), settings=private_settings)
    assert (await client.post(path(conversation, reply))).status_code == 502
    assert (await client.post(path(conversation, reply))).status_code == 429


def test_limiter_blocks_concurrency_and_cooldown_per_user():
    now = [0.0]
    limiter = read_aloud_api.ReadAloudLimiter(lambda: now[0])
    with limiter.hold("alice"):
        with pytest.raises(HTTPException) as error:
            with limiter.hold("alice"):
                pass
        assert error.value.status_code == 429
        with limiter.hold("bob"):
            pass
    now[0] = 2.9
    with pytest.raises(HTTPException):
        with limiter.hold("alice"):
            pass
    now[0] = 3
    with limiter.hold("alice"):
        pass


async def test_disconnect_cancels_upstream_synthesis(private_settings, monkeypatch):
    cancelled = asyncio.Event()

    async def synthesize(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def receive():
        return {"type": "http.disconnect"}

    monkeypatch.setattr(volcengine_tts, "synthesize", synthesize)
    backend = build_faked(private_settings, FakeLLM([]))
    try:
        with pytest.raises(HTTPException) as error:
            await read_aloud_api._audio(Request({"type": "http"}, receive), backend, "text")
        assert error.value.status_code == 499
        assert cancelled.is_set()
    finally:
        await backend.aclose()


async def test_plain_text_fallback_is_explicitly_chinese(
    make_client, private_settings, saved_reply, monkeypatch,
):
    conversation, reply = saved_reply
    with sqlite3.connect(private_settings.database_path) as database:
        database.execute("UPDATE messages SET ja = NULL, text = ? WHERE id = ?", ("你好", reply.id))
    seen = []

    async def synthesize(settings, text, *, language):
        seen.append((text, language))
        return b"mp3"

    monkeypatch.setattr(volcengine_tts, "synthesize", synthesize)
    client = make_client(FakeLLM([]), settings=private_settings)
    assert (await client.post(path(conversation, reply))).status_code == 200
    assert seen == [("你好", "zh-cn")]
