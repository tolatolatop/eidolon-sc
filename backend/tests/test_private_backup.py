"""The private release's encrypted snapshots preserve data and refuse unsafe restores."""

import os
import runpy
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet, InvalidToken

operations = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "deploy/sekai/private_backup.py")
)
snapshot = operations["snapshot"]
restore = operations["restore"]


def test_snapshot_restores_a_consistent_wal_database_and_is_not_plaintext(tmp_path: Path):
    source = tmp_path / "live.db"
    key = Fernet.generate_key()
    with sqlite3.connect(source) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE dialogue (text TEXT)")
        db.execute("INSERT INTO dialogue VALUES (?)", ("测试对话",))
        db.commit()
        archive = snapshot(source, tmp_path / "backups", key, datetime.now(UTC))
    assert b"SQLite format" not in archive.read_bytes()
    assert "测试对话".encode() not in archive.read_bytes()
    output = tmp_path / "restored.db"
    restore(archive, output, key)
    with sqlite3.connect(output) as restored:
        assert restored.execute("SELECT text FROM dialogue").fetchall() == [("测试对话",)]
        assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    with pytest.raises(FileExistsError):
        restore(archive, output, key)
    with pytest.raises(InvalidToken):
        restore(archive, tmp_path / "wrong-key.db", Fernet.generate_key())
    assert not (tmp_path / "wrong-key.db").exists()


def test_retention_only_expires_snapshots_after_a_new_success(tmp_path: Path):
    source = tmp_path / "live.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE sample (id INTEGER)")
    directory = tmp_path / "backups"
    key = Fernet.generate_key()
    now = datetime.now(UTC)
    old = snapshot(source, directory, key, now - timedelta(days=15))
    expired = (now - timedelta(days=15)).timestamp()
    os.utime(old, (expired, expired))
    unrelated = directory / "keep.txt"
    unrelated.write_text("unrelated")
    current = snapshot(source, directory, key, now)
    assert current.exists() and not old.exists()
    assert unrelated.read_text() == "unrelated"
    assert (directory / ".last-success").exists()
