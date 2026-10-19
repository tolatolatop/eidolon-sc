"""Encrypted local SQLite snapshots for the private release, separate from its live volume."""

import argparse
import os
import sqlite3
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet

RETENTION = timedelta(days=14)
INTERVAL = 24 * 60 * 60


def snapshot(database: Path, directory: Path, key: bytes, now: datetime) -> Path:
    """Capture a consistent SQLite backup, encrypt it, then publish it atomically."""
    cipher = Fernet(key)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory() as work:
        plain = Path(work) / "snapshot.db"
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as source:
            with sqlite3.connect(plain) as target:
                source.backup(target)
        encrypted = cipher.encrypt(plain.read_bytes())
    target = directory / f"sekai-{now.astimezone(UTC):%Y%m%dT%H%M%S%fZ}.db.fernet"
    temporary = target.with_suffix(".pending")
    with temporary.open("xb") as output:
        temporary.chmod(0o600)
        output.write(encrypted)
    temporary.replace(target)
    for earlier in directory.glob("sekai-*.db.fernet"):
        if earlier != target and earlier.is_file() and earlier.stat().st_mtime < (
            now - RETENTION
        ).timestamp():
            earlier.unlink()
    (directory / ".last-success").touch()
    return target


def restore(archive: Path, output: Path, key: bytes) -> None:
    """Verify and decrypt a snapshot to a new file; never overwrite an existing database."""
    plain = Fernet(key).decrypt(archive.read_bytes())
    with tempfile.TemporaryDirectory() as work:
        check = Path(work) / "check.db"
        check.write_bytes(plain)
        with sqlite3.connect(check) as database:
            if database.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("snapshot integrity check failed")
    with output.open("xb") as destination:
        output.chmod(0o600)
        destination.write(plain)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("loop", "snapshot", "verify", "restore"))
    parser.add_argument("archive", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action in {"verify", "restore"} and args.archive is None:
        parser.error("archive is required")
    if args.action == "restore" and args.output is None:
        parser.error("--output is required; an existing file is never overwritten")
    try:
        key = os.environ["SEKAI_BACKUP_KEY"].encode("ascii")
        Fernet(key)
        if args.action == "restore":
            restore(args.archive, args.output, key)
        elif args.action == "verify":
            with tempfile.TemporaryDirectory() as work:
                restore(args.archive, Path(work) / "restored.db", key)
        else:
            while True:
                try:
                    archive = snapshot(
                        Path("/data/eidolon.db"), Path("/backups"), key, datetime.now(UTC)
                    )
                    print(f"snapshot saved: {archive.name}", flush=True)
                except (OSError, ValueError, sqlite3.Error) as error:
                    if args.action == "snapshot":
                        raise
                    print(f"snapshot failed: {type(error).__name__}", file=sys.stderr, flush=True)
                    time.sleep(300)
                    continue
                if args.action == "snapshot":
                    break
                time.sleep(INTERVAL)
    except Exception as error:
        # Never include encrypted contents, keys, or database rows in diagnostics.
        print(f"backup operation failed: {type(error).__name__}", file=sys.stderr)
        return 1
    print("backup operation completed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
