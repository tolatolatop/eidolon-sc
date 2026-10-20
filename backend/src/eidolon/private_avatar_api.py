"""Fixed, authenticated classic Miku preview; never a generic file server."""

import json
import os
import stat
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response

from eidolon.assembly import Backend
from eidolon.sessions import UserId

BASE = "/api/private-avatar/assets/"
MOTIONS = frozenset(
    [f"motions/miku_m_{i:02}.mtn" for i in range(1, 7)]
    + ["motions/miku_shake_01.mtn", "motions/miku_idle_01.mtn"]
)
ASSETS = {
    "miku.model.json": ("application/json", 64 * 1024),
    "miku.physics.json": ("application/json", 64 * 1024),
    "miku.moc": ("application/octet-stream", 2 * 1024 * 1024),
    "miku.2048/texture_00.png": ("image/png", 8 * 1024 * 1024),
    "live2d.min.js": ("application/javascript", 512 * 1024),
    **{name: ("application/octet-stream", 128 * 1024) for name in MOTIONS},
}
HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


def _read(root: Path, name: str) -> bytes:
    """Open beneath the trusted admin root without following asset symlinks.

    The root's ancestor directories belong to the trusted deployment configuration.
    Each asset component, including the root's final component, uses no-follow.
    """
    if name not in ASSETS:
        raise ValueError("unknown asset")
    limit = ASSETS[name][1]
    parts = name.split("/")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory,
            )
            os.close(directory)
            directory = child
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory,
        )
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
                raise ValueError("invalid asset size or type")
            data = stream.read(limit + 1)
            if not 0 < len(data) <= limit:
                raise ValueError("invalid asset size")
            return data
    finally:
        os.close(directory)


def _model(data: bytes) -> dict:
    """Accept only this legacy schema, so no sound or external references reach PIXI."""
    model = json.loads(data)
    if not isinstance(model, dict) or set(model) - {
        "version", "model", "textures", "physics", "motions",
    }:
        raise ValueError("unknown model fields")
    if (model.get("model") != "miku.moc"
            or model.get("textures") != ["miku.2048/texture_00.png"]
            or model.get("physics") != "miku.physics.json"):
        raise ValueError("invalid model references")
    motions = model.get("motions")
    if not isinstance(motions, dict) or set(motions) != {"idle", "null"}:
        raise ValueError("invalid motion groups")
    for group, entries in motions.items():
        if not isinstance(entries, list) or not 1 <= len(entries) <= 8:
            raise ValueError("invalid motion list")
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"file"}:
                raise ValueError("sound and extra motion fields are forbidden")
            expected = {"motions/miku_idle_01.mtn"} if group == "idle" else MOTIONS
            if not isinstance(entry["file"], str) or entry["file"] not in expected:
                raise ValueError("invalid motion reference")
    # Version is metadata, not executable input; return a fixed value.
    return {**model, "version": "Sample 1.0.0"}


def add_private_avatar_routes(app: FastAPI, backend: Backend) -> None:
    settings = backend.settings

    def private_only() -> Path | None:
        if settings.private_password_hash is None:
            raise HTTPException(404, "没有此功能", headers=HEADERS)
        return settings.private_live2d_dir

    @app.get("/api/private-avatar")
    def availability(user_id: UserId, response: Response) -> dict:
        root = private_only()
        response.headers.update(HEADERS)
        try:
            if root is None:
                return {"available": False}
            _model(_read(root, "miku.model.json"))
            # Fixed, small asset set; readiness also verifies all files and size bounds.
            for name in ASSETS.keys() - {"miku.model.json"}:
                _read(root, name)
        except (OSError, ValueError, TypeError, RecursionError):
            return {"available": False}
        return {
            "available": True,
            "model_url": BASE + "miku.model.json",
            "script_url": BASE + "live2d.min.js",
        }

    @app.get("/api/private-avatar/assets/{asset_path:path}")
    def asset(asset_path: str, user_id: UserId) -> Response:
        root = private_only()
        if root is None or asset_path not in ASSETS:
            raise HTTPException(404, "没有此资源", headers=HEADERS)
        try:
            data = _read(root, asset_path)
            if asset_path == "miku.model.json":
                data = json.dumps(_model(data), separators=(",", ":")).encode()
        except (OSError, ValueError, TypeError, RecursionError):
            raise HTTPException(404, "资源不可用", headers=HEADERS) from None
        return Response(data, media_type=ASSETS[asset_path][0], headers=HEADERS)
