"""Private password login: bounded guesses, one owner, consent and explicit origin."""

import asyncio
import hashlib
import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from eidolon import private_login
from eidolon.accounts import SignInRefused
from eidolon.config import Settings
from eidolon.private_login import (
    LoginCooling, PasswordLogin, hash_password, valid_password_hash, verify_password,
)
from eidolon.sessions import SESSION_COOKIE, origin_allowed
from tests.conftest import ClientFactory, agree_to_terms
from tests.fakes import FakeClock, FakeLLM, build_faked
from tests.test_delete_account import files_holding

PASSWORD = "a-private-test-password"


@pytest.fixture(scope="module")
def password_hash() -> str:
    return hash_password(PASSWORD)


@pytest.fixture
def private_settings(settings: Settings, password_hash: str) -> Settings:
    return replace(
        settings, dev_login=False, private_password_hash=password_hash,
        private_origin="http://localhost:3000",
    )


@pytest.fixture(autouse=True)
def login_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr(
        private_login, "LOGIN_LIMITER", PasswordLogin(lambda: clock().timestamp())
    )
    return clock


def test_hash_uses_fixed_scrypt_parameters_and_fresh_random_salt(password_hash: str):
    assert valid_password_hash(password_hash)
    assert hash_password(PASSWORD) != password_hash
    _, salt, digest = password_hash.split(":")
    assert hashlib.scrypt(
        PASSWORD.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32
    ).hex() == digest
    assert verify_password(PASSWORD, password_hash)
    assert not verify_password(PASSWORD + "x", password_hash)


@pytest.mark.parametrize("password", ["", "short", "x" * 257])
def test_hash_rejects_invalid_password_lengths(password: str):
    with pytest.raises(ValueError, match="8～256"):
        hash_password(password)


@pytest.mark.parametrize("password", ["x" * 8, "你" * 256])
def test_password_length_boundaries_and_unicode(password: str):
    assert verify_password(password, hash_password(password))


@pytest.mark.parametrize(
    "value", ["plaintext-secret", "scrypt-v2:" + "a" * 32 + ":" + "b" * 64,
              "scrypt-v1:" + "A" * 32 + ":" + "b" * 64,
              "scrypt-v1:" + "a" * 31 + ":" + "b" * 64,
              "scrypt-v1:" + "a" * 32 + ":" + "b" * 65]
)
def test_bad_hash_is_rejected_without_revealing_it(settings: Settings, value: str):
    assert not verify_password(PASSWORD, value)
    with pytest.raises(RuntimeError) as error:
        replace(settings, dev_login=False, private_password_hash=value)
    assert value not in str(error.value)


def test_private_configuration_is_loaded_and_kept_out_of_repr(
    monkeypatch: pytest.MonkeyPatch, password_hash: str
):
    for name, value in {
        "CHAT_LLM_BASE_URL": "http://llm.invalid/v1", "CHAT_LLM_API_KEY": "k",
        "CHAT_LLM_MODEL": "m", "EIDOLON_PRIVATE_PASSWORD_HASH": password_hash,
        "EIDOLON_PRIVATE_ORIGIN": "http://192.168.1.10:3300",
    }.items():
        monkeypatch.setenv(name, value)
    loaded = Settings.from_env()
    assert loaded.private_password_hash == password_hash
    assert loaded.private_origin == "http://192.168.1.10:3300"
    assert password_hash not in repr(loaded)


def test_private_password_and_development_login_are_mutually_exclusive(
    settings: Settings, password_hash: str
):
    with pytest.raises(RuntimeError, match="EIDOLON_DEV_LOGIN"):
        replace(settings, private_password_hash=password_hash)


@pytest.mark.parametrize(
    "origin", ["ftp://example.com", "https://example.com/", "https://example.com/path",
               "http://user:pass@localhost", "http://localhost?x=1", "http://localhost#x",
               "http://localhost?", "http://localhost#", "http://localhost:",
               "http://localhost:65536", "http://localhost:0", "localhost:3000",
               "http://local\\host", "http://local%68ost", "http://local\nhost"]
)
def test_private_origin_must_be_a_complete_plain_http_origin(
    private_settings: Settings, origin: str
):
    with pytest.raises(RuntimeError, match="EIDOLON_PRIVATE_ORIGIN"):
        replace(private_settings, private_origin=origin)


def test_private_origin_requires_a_password(settings: Settings):
    with pytest.raises(RuntimeError, match="EIDOLON_PRIVATE_ORIGIN"):
        replace(settings, dev_login=False, private_origin="http://localhost:3000")


@pytest.mark.parametrize(
    "origin", ["http://LOCALHOST:18739", "https://Private.Example", "HTTP://localhost:18739",
               "http://localhost:80", "https://private.example:443",
               "http://localhost:018739", "http://[0:0:0:0:0:0:0:1]:18739",
               "http://[2001:DB8::ABCD]:18739", "https://[::1]:443",
               "http://127.1:18739", "http://2130706433:18739", "http://例子.测试:18739"]
)
def test_noncanonical_origin_is_rejected_before_login(
    private_settings: Settings, origin: str
):
    with pytest.raises(RuntimeError, match="规范"):
        replace(private_settings, private_origin=origin)


@pytest.mark.parametrize(
    "origin", ["http://192.168.1.10:3300", "https://private.example", "http://[::1]:3000",
               "http://[2001:db8::abcd]:18739", "https://[::1]", "http://localhost",
               "http://localhost:443", "https://private.example:80"]
)
def test_private_origin_is_exact_and_takes_priority_over_domain(
    private_settings: Settings, origin: str
):
    configured = replace(private_settings, private_origin=origin, domain="unused.example")
    assert configured.public_origin == origin
    assert origin_allowed(origin, False, configured)
    assert origin_allowed(origin, True, configured)
    assert not origin_allowed(None, False, configured)
    assert not origin_allowed(None, True, configured)
    for wrong in [origin + "/", "http://localhost:3000", "https://unused.example"]:
        if wrong != origin:
            assert not origin_allowed(wrong, False, configured)
            assert not origin_allowed(wrong, True, configured)


async def test_disabled_private_login_has_no_route_or_discovery_field(
    make_client: ClientFactory,
):
    client = make_client(FakeLLM(), user=None)
    assert "private_login" not in (await client.get("/api/auth/providers")).json()
    result = await client.post("/api/auth/private-login", json={"password": PASSWORD})
    assert result.status_code == 404


async def test_private_login_creates_only_its_owner_and_preserves_consent(
    make_client: ClientFactory, private_settings: Settings,
):
    existing = make_client(FakeLLM(), "同行者")
    existing_id = (await existing.get("/api/account")).json()["id"]
    client = make_client(FakeLLM(), user=None, settings=private_settings)
    assert (await client.get("/api/auth/providers")).json()["private_login"] is True
    res = await client.post(
        "/api/auth/private-login", json={"password": PASSWORD, "name": "someone-else"}
    )
    assert res.status_code == 204
    cookie = res.headers["set-cookie"]
    assert SESSION_COOKIE in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Secure" not in cookie
    assert (await client.get("/api/account")).status_code == 428
    assert (await client.post("/api/conversations", json={"character_id": "mano"})).status_code == 428
    await agree_to_terms(client)
    account = (await client.get("/api/account")).json()
    assert account["name"] == "同行者" and account["id"] != existing_id
    assert account["sign_in_methods"] == [
        {"provider": "private", "display_name": "同行者", "email": None}
    ]
    assert (await client.delete("/api/account/sign-in-methods/private")).status_code == 409
    other = make_client(FakeLLM(), user=None, settings=private_settings)
    assert (await other.post("/api/auth/private-login", json={"password": PASSWORD})).status_code == 204
    assert (await other.get("/api/account")).json()["id"] == account["id"]
    assert (await client.post("/api/auth/dev-login", json={"name": "someone"})).status_code == 404


@pytest.mark.parametrize("password", ["incorrect-password", "", "short", "x" * 257, None, 1, [], "\ud800" + "x" * 8])
async def test_incorrect_credentials_are_uniform_and_never_echoed(
    make_client: ClientFactory, private_settings: Settings, password: object,
    caplog: pytest.LogCaptureFixture,
):
    client = make_client(FakeLLM(), user=None, settings=private_settings)
    with caplog.at_level(logging.DEBUG):
        result = await client.post(
            "/api/auth/private-login", content=json.dumps({"password": password}),
            headers={"Content-Type": "application/json"},
        )
    assert result.status_code == 401
    assert result.json() == {"detail": "访问口令不正确"}
    assert "set-cookie" not in result.headers
    if isinstance(password, str) and len(password) >= 8:
        assert password not in caplog.text


@pytest.mark.parametrize("body", ["{}", "[]", "null", "not-json"])
async def test_missing_or_malformed_credentials_have_the_same_failure(
    make_client: ClientFactory, private_settings: Settings, body: str,
):
    client = make_client(FakeLLM(), user=None, settings=private_settings)
    response = await client.post("/api/auth/private-login", content=body)
    assert response.status_code == 401
    assert response.json() == {"detail": "访问口令不正确"}


async def test_failures_are_global_and_correct_password_cannot_bypass_cooldown(
    make_client: ClientFactory, private_settings: Settings, login_clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
):
    clients = [make_client(FakeLLM(), user=None, settings=private_settings) for _ in range(2)]
    for index in range(5):
        result = await clients[index % 2].post(
            "/api/auth/private-login", json={"password": "wrong-password"},
            headers={"X-Forwarded-For": f"10.0.0.{index}"},
        )
        assert result.status_code == 401
    original = private_login.verify_password

    def unexpected_hash(*args: object) -> bool:
        pytest.fail("scrypt must not execute during cooldown")

    monkeypatch.setattr(private_login, "verify_password", unexpected_hash)
    blocked = await clients[0].post("/api/auth/private-login", json={"password": PASSWORD})
    assert blocked.status_code == 429 and blocked.headers["retry-after"] == "60"
    login_clock.advance(seconds=59.5)
    blocked = await clients[1].post("/api/auth/private-login", json={"password": PASSWORD})
    assert blocked.status_code == 429 and blocked.headers["retry-after"] == "1"
    login_clock.advance(seconds=0.5)
    monkeypatch.setattr(private_login, "verify_password", original)
    assert (await clients[0].post("/api/auth/private-login", json={"password": PASSWORD})).status_code == 204


def test_concurrent_failures_cannot_race_past_the_budget(password_hash: str):
    limiter = PasswordLogin(lambda: 0.0)

    def attempt(_: int) -> str:
        try:
            assert not limiter.verify("wrong-password", password_hash)
            return "failed"
        except LoginCooling:
            return "limited"

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(attempt, range(10)))
    assert results.count("failed") == 5 and results.count("limited") == 5


async def test_success_does_not_reset_failures(
    make_client: ClientFactory, private_settings: Settings,
):
    client = make_client(FakeLLM(), user=None, settings=private_settings)
    for _ in range(4):
        await client.post("/api/auth/private-login", json={"password": "wrong-password"})
    assert (await client.post("/api/auth/private-login", json={"password": PASSWORD})).status_code == 204
    assert (await client.post("/api/auth/private-login", json={"password": "wrong-password"})).status_code == 401
    assert (await client.post("/api/auth/private-login", json={"password": PASSWORD})).status_code == 429


async def test_banning_and_deleting_the_private_owner_keeps_the_identity_banned(
    private_settings: Settings,
):
    backend = build_faked(private_settings, FakeLLM(), identity_providers={})
    try:
        user = backend.accounts.private_sign_in()
        backend.store.set_banned(user.id, backend.clock())
        with pytest.raises(SignInRefused, match="banned"):
            backend.accounts.private_sign_in()
        await backend.accounts.delete(user.id)
        with pytest.raises(SignInRefused, match="banned"):
            backend.accounts.private_sign_in()
    finally:
        await backend.aclose()


async def test_banned_owner_cannot_receive_a_session(
    make_client: ClientFactory, private_settings: Settings,
):
    client = make_client(FakeLLM(), user=None, settings=private_settings)
    await client.post("/api/auth/private-login", json={"password": PASSWORD})
    await client.post("/api/auth/logout")
    with sqlite3.connect(private_settings.database_path) as db:
        db.execute("UPDATE users SET banned_at = '2026-09-25T00:00:00+00:00'")
    response = await client.post("/api/auth/private-login", json={"password": PASSWORD})
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


async def test_unbanned_owner_can_delete_data_and_sign_up_afresh(
    make_client: ClientFactory, private_settings: Settings,
):
    client = make_client(FakeLLM(), user=None, settings=private_settings)
    await client.post("/api/auth/private-login", json={"password": PASSWORD})
    await agree_to_terms(client)
    old_id = (await client.get("/api/account")).json()["id"]
    assert (await client.post("/api/account/delete", json={"confirm": True})).status_code == 204
    assert (await client.get("/api/account")).status_code == 401
    await client.post("/api/auth/private-login", json={"password": PASSWORD})
    assert (await client.get("/api/account")).status_code == 428
    await agree_to_terms(client)
    assert (await client.get("/api/account")).json()["id"] != old_id
    assert not files_holding(private_settings.database_path, PASSWORD)


@pytest.mark.parametrize("scheme", ["http", "https"])
async def test_explicit_lan_origin_and_secure_cookie_for_https_only(
    make_client: ClientFactory, private_settings: Settings, scheme: str,
):
    origin = f"{scheme}://192.168.1.10:3300"
    configured = replace(private_settings, private_origin=origin)
    client = make_client(FakeLLM(), user=None, settings=configured)
    client.base_url = origin
    client.headers["Origin"] = origin
    wrong = await client.post(
        "/api/auth/private-login", json={"password": PASSWORD},
        headers={"Origin": "http://localhost:3000"},
    )
    assert wrong.status_code == 403
    result = await client.post("/api/auth/private-login", json={"password": PASSWORD})
    assert result.status_code == 204
    assert ("Secure" in result.headers["set-cookie"]) is (scheme == "https")
    await agree_to_terms(client)
    assert (await client.get("/api/account")).status_code == 200
    client.headers.pop("Origin")
    assert (await client.post("/api/auth/logout")).status_code == 403
    client.headers["Origin"] = origin
    signed_out = await client.post("/api/auth/logout")
    assert signed_out.status_code == 204
    assert ("Secure" in signed_out.headers["set-cookie"]) is (scheme == "https")


async def test_two_simultaneous_correct_logins_get_one_owner(
    make_client: ClientFactory, private_settings: Settings,
):
    clients = [make_client(FakeLLM(), user=None, settings=private_settings) for _ in range(2)]
    results = await asyncio.gather(*[
        client.post("/api/auth/private-login", json={"password": PASSWORD}) for client in clients
    ])
    assert all(result.status_code == 204 for result in results)
    for client in clients:
        await agree_to_terms(client)
    accounts = [(await client.get("/api/account")).json() for client in clients]
    assert accounts[0]["id"] == accounts[1]["id"]
