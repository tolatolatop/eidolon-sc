import json
from dataclasses import replace

import pytest

from eidolon.private_avatar_api import ASSETS, BASE, HEADERS
from eidolon.sessions import SESSION_COOKIE
from tests.fakes import FakeLLM
from tests.test_read_aloud_api import private_hash, private_settings  # noqa: F401


@pytest.fixture
def avatar_dir(tmp_path):
    root = tmp_path / "avatar"
    model = {
        "version": "Sample 1.0.0", "model": "miku.moc",
        "textures": ["miku.2048/texture_00.png"], "physics": "miku.physics.json",
        "motions": {
            "idle": [{"file": "motions/miku_idle_01.mtn"}],
            "null": [{"file": "motions/miku_m_01.mtn"}],
        },
    }
    for name in ASSETS:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(json.dumps(model).encode() if name == "miku.model.json" else b"sample")
    return root


async def test_private_readiness_and_all_fixed_assets(make_client, private_settings, avatar_dir):
    client = make_client(FakeLLM([]), settings=replace(private_settings, private_live2d_dir=avatar_dir))
    response = await client.get("/api/private-avatar")
    assert response.json() == {
        "available": True, "model_url": BASE + "miku.model.json",
        "script_url": BASE + "live2d.min.js",
    }
    assert str(avatar_dir) not in response.text
    for name, (media_type, _) in ASSETS.items():
        asset = await client.get(BASE + name)
        assert asset.status_code == 200
        assert asset.headers["content-type"].startswith(media_type)
        for key, value in HEADERS.items():
            assert asset.headers[key] == value
    assert response.headers["cache-control"] == "private, no-store"


async def test_private_login_and_consent_required(make_client, private_settings, avatar_dir):
    settings = replace(private_settings, private_live2d_dir=avatar_dir)
    client = make_client(FakeLLM([]), user=None, settings=settings)
    for path in ["/api/private-avatar", BASE + "live2d.min.js"]:
        assert (await client.get(path)).status_code == 401
    assert (await client.post("/api/auth/private-login", json={"password": "a-fake-test-password"})).status_code == 204
    for path in ["/api/private-avatar", BASE + "miku.model.json"]:
        assert (await client.get(path)).status_code == 428
    client.cookies.delete(SESSION_COOKIE)
    assert (await client.get(BASE + "miku.moc")).status_code == 401


async def test_unconfigured_missing_and_public_deployment(make_client, settings, private_settings, avatar_dir):
    private = make_client(FakeLLM([]), settings=private_settings)
    assert (await private.get("/api/private-avatar")).json() == {"available": False}
    assert (await private.get(BASE + "miku.moc")).status_code == 404
    normal = make_client(FakeLLM([]), settings=replace(settings, private_live2d_dir=avatar_dir))
    assert (await normal.get("/api/private-avatar")).status_code == 404
    assert (await normal.get(BASE + "live2d.min.js")).status_code == 404
    (avatar_dir / "miku.moc").unlink()
    broken = make_client(FakeLLM([]), settings=replace(private_settings, private_live2d_dir=avatar_dir))
    assert (await broken.get("/api/private-avatar")).json() == {"available": False}


@pytest.mark.parametrize("path", [
    "other.png", "miku.model.json.bak", "", "%2e%2e/config.py", "%2Fetc/passwd",
    "miku.2048/%2e%2e/miku.moc", "motions%5Cmiku_m_01.mtn", "miku.moc%00",
    "https://example.com/file.png", "motions/miku_m_07.mtn", "%252e%252e/secret",
])
async def test_rejects_paths_outside_exact_allowlist(make_client, private_settings, avatar_dir, path):
    client = make_client(FakeLLM([]), settings=replace(private_settings, private_live2d_dir=avatar_dir))
    assert (await client.get(BASE + path)).status_code == 404


@pytest.mark.parametrize("change", [
    {"model": "https://example.com/a.moc"}, {"textures": ["//example.com/a.png"]},
    {"physics": "../private.json"}, {"pose": "private.json"},
    {"motions": {"idle": [{"file": "motions/miku_idle_01.mtn", "sound": "remote.mp3"}]}},
    {"motions": {"idle": [{"file": "motions/miku_idle_01.mtn"}], "null": [{"file": "https://evil/a.mtn"}]}},
    {"motions": []}, {"expressions": [{"file": "outside.json"}]},
])
async def test_rejects_unsafe_model_references(make_client, private_settings, avatar_dir, change):
    path = avatar_dir / "miku.model.json"
    model = json.loads(path.read_text())
    path.write_text(json.dumps({**model, **change}))
    client = make_client(FakeLLM([]), settings=replace(private_settings, private_live2d_dir=avatar_dir))
    assert (await client.get("/api/private-avatar")).json() == {"available": False}
    assert (await client.get(BASE + "miku.model.json")).status_code == 404


@pytest.mark.parametrize("kind", ["file", "directory", "root", "oversized", "empty", "fifo"])
async def test_file_boundaries(make_client, private_settings, avatar_dir, tmp_path, kind):
    root = avatar_dir
    asset = avatar_dir / "miku.moc"
    if kind in {"file", "root", "directory"}:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "miku.moc").write_bytes(b"private")
        if kind == "file":
            asset.unlink()
            asset.symlink_to(outside / "miku.moc")
        elif kind == "directory":
            (avatar_dir / "motions").rename(outside / "motions")
            (avatar_dir / "motions").symlink_to(outside / "motions")
            asset = avatar_dir / "motions/miku_m_01.mtn"
        else:
            root = tmp_path / "linked-root"
            root.symlink_to(avatar_dir)
    elif kind == "oversized":
        asset.write_bytes(b"x" * (ASSETS["miku.moc"][1] + 1))
    elif kind == "empty":
        asset.write_bytes(b"")
    else:
        import os
        asset.unlink()
        os.mkfifo(asset)
    client = make_client(FakeLLM([]), settings=replace(private_settings, private_live2d_dir=root))
    assert (await client.get("/api/private-avatar")).json() == {"available": False}
    assert (await client.get(BASE + str(asset.relative_to(avatar_dir)))).status_code == 404
