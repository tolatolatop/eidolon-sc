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
    with sqlite3.connect(private_settings.database_path) as database:
        database.execute("UPDATE messages SET zh = NULL, text = ? WHERE id = ?", (text, message.id))
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
        database.execute("UPDATE messages SET ja = NULL, zh = NULL, text = ? WHERE id = ?", ("你好", reply.id))
    seen = []

    async def synthesize(settings, text, *, language):
        seen.append((text, language))
        return b"mp3"

    monkeypatch.setattr(volcengine_tts, "synthesize", synthesize)
    client = make_client(FakeLLM([]), settings=private_settings)
    assert (await client.post(path(conversation, reply))).status_code == 200
    assert seen == [("你好", "zh-cn")]


@pytest.mark.parametrize("healthy", [True, False])
async def test_local_availability_checks_real_health(make_client, private_settings, monkeypatch, healthy):
    from eidolon import local_tts

    async def ready(url):
        assert url == "http://tts:8000"
        return healthy

    monkeypatch.setattr(local_tts, "ready", ready)
    client = make_client(FakeLLM([]), settings=replace(private_settings, local_tts_url="http://tts:8000", volcengine_tts_api_key=None))
    response = await client.get("/api/read-aloud")
    result = response.json()
    assert result["available"] is healthy
    assert result["provider"] == "kokoro"
    assert result["languages"] == ["ja", "zh-cn"]
    assert result["reason"] == ("ready" if healthy else "unready")
    assert response.headers["cache-control"] == "no-store"


async def test_local_provider_preferred_and_never_falls_back(make_client, private_settings, saved_reply, monkeypatch):
    from eidolon import local_tts

    conversation, reply = saved_reply
    seen = []

    async def synthesize(url, text, *, language):
        seen.append((url, text, language))
        raise HTTPException(503, "本地朗读服务暂时不可用")

    async def never(*args, **kwargs):
        pytest.fail("local TTS must never fall back to cloud")

    monkeypatch.setattr(local_tts, "synthesize", synthesize)
    monkeypatch.setattr(volcengine_tts, "synthesize", never)
    client = make_client(FakeLLM([]), settings=replace(private_settings, local_tts_url="http://tts:8000"))
    response = await client.post(path(conversation, reply))
    assert response.status_code == 503
    assert "火山" not in response.text
    assert seen == [("http://tts:8000", "はい", "ja")]


async def test_local_wav_and_chinese_fallback(make_client, private_settings, saved_reply, monkeypatch):
    from eidolon import local_tts
    from tests.test_local_tts import wav

    conversation, reply = saved_reply
    with sqlite3.connect(private_settings.database_path) as database:
        database.execute("UPDATE messages SET ja = NULL, zh = NULL, text = ? WHERE id = ?", ("你好", reply.id))

    async def synthesize(url, text, *, language):
        assert (text, language) == ("你好", "zh-cn")
        return wav()

    monkeypatch.setattr(local_tts, "synthesize", synthesize)
    client = make_client(FakeLLM([]), settings=replace(private_settings, local_tts_url="http://tts:8000"))
    response = await client.post(path(conversation, reply))
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["cache-control"] == "no-store"
    assert response.content == wav()


async def test_local_disabled_and_oversize_do_not_call_provider(make_client, private_settings, saved_reply, monkeypatch):
    from eidolon import local_tts

    conversation, reply = saved_reply

    async def never(*args, **kwargs):
        pytest.fail("disabled/oversized synthesis")

    monkeypatch.setattr(local_tts, "synthesize", never)
    disabled = make_client(FakeLLM([]), settings=replace(private_settings, local_tts_url="http://tts:8000", read_aloud_enabled=False))
    assert (await disabled.get("/api/read-aloud")).json() == {"available": False, "enabled": False}
    assert (await disabled.post(path(conversation, reply))).status_code == 404
    with sqlite3.connect(private_settings.database_path) as database:
        database.execute("UPDATE messages SET ja = ? WHERE id = ?", ("あ" * 301, reply.id))
    client = make_client(FakeLLM([]), settings=replace(private_settings, local_tts_url="http://tts:8000"))
    assert (await client.post(path(conversation, reply))).status_code == 422


async def test_disconnect_cancels_local_upstream(private_settings, monkeypatch):
    from eidolon import local_tts

    cancelled = asyncio.Event()

    async def synthesize(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def receive():
        return {"type": "http.disconnect"}

    monkeypatch.setattr(local_tts, "synthesize", synthesize)
    backend = build_faked(replace(private_settings, local_tts_url="http://tts"), FakeLLM([]))
    try:
        with pytest.raises(HTTPException) as error:
            await read_aloud_api._audio(Request({"type": "http"}, receive), backend, "text")
        assert error.value.status_code == 499
        assert cancelled.is_set()
    finally:
        await backend.aclose()


@pytest.mark.parametrize("ja,zh,legacy,expected,language", [
    (" はい ", "中文", "旧文字", "はい", "ja"),
    ("   ", "[happy] 中文", "旧文字", "中文", "zh-cn"),
    ("[happy]", "  中文 ", "旧文字", "中文", "zh-cn"),
    (None, None, "[happy] 旧文字", "旧文字", "zh-cn"),
])
async def test_saved_reply_uses_first_nonempty_cue_free_language(
    make_client, private_settings, saved_reply, monkeypatch, ja, zh, legacy, expected, language,
):
    from eidolon import local_tts

    conversation, reply = saved_reply
    with sqlite3.connect(private_settings.database_path) as database:
        database.execute("UPDATE messages SET ja = ?, zh = ?, text = ? WHERE id = ?", (ja, zh, legacy, reply.id))

    async def synthesize(url, text, *, language):
        assert text == expected
        assert language == expected_language
        return b"wav"

    expected_language = language
    monkeypatch.setattr(local_tts, "synthesize", synthesize)
    client = make_client(FakeLLM([]), settings=replace(private_settings, local_tts_url="http://tts"))
    assert (await client.post(path(conversation, reply))).status_code == 200
