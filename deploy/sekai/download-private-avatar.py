"""Install the pinned legacy Miku sample into a private runtime directory."""

import argparse
import hashlib
import json
import os
import stat
import urllib.parse
import urllib.request
from pathlib import Path


def verify(path: Path, item: dict) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    digest = hashlib.sha256()
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != item["size"]:
            raise ValueError(f"Invalid existing asset: {path.name}")
        remaining = item["size"] + 1
        while remaining and (chunk := source.read(min(1024 * 1024, remaining))):
            digest.update(chunk)
            remaining -= len(chunk)
    if remaining != 1 or digest.hexdigest() != item["sha256"]:
        raise ValueError(f"Checksum mismatch: {path.name}; refusing replacement")


def download(directory: Path) -> None:
    manifest_path = (
        Path(__file__).resolve().parents[2] / "examples/project-sekai/assets.json"
    )
    manifest = json.loads(manifest_path.read_text())["dynamic_model"]
    new_directory = not directory.exists()
    directory.mkdir(parents=True, exist_ok=True, mode=0o755)
    if new_directory:
        directory.chmod(0o755)
    if directory.is_symlink():
        raise ValueError("Model directory must not be a symlink")
    root = directory.resolve()
    for item in manifest["files"]:
        relative = Path(item["path"])
        url = urllib.parse.urlsplit(item["url"])
        if (relative.is_absolute() or ".." in relative.parts
                or url.scheme != "https" or url.hostname != "raw.githubusercontent.com"
                or item["size"] > 2 * 1024 * 1024):
            raise ValueError("Unexpected asset manifest entry")
        target = directory / relative
        if any((directory / Path(*relative.parts[:i])).is_symlink()
               for i in range(1, len(relative.parts) + 1)):
            raise ValueError("Asset path must not contain symlinks")
        if not target.resolve().is_relative_to(root):
            raise ValueError("Asset path leaves model directory")
        if target.exists():
            verify(target, item)
            continue
        new_parent = not target.parent.exists()
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        if new_parent:
            target.parent.chmod(0o755)
        partial = target.with_name(target.name + ".part")
        created = False
        try:
            with partial.open("xb") as output:
                created = True
                with urllib.request.urlopen(item["url"], timeout=30) as response:
                    data = response.read(item["size"] + 1)
                if len(data) != item["size"]:
                    raise ValueError("Asset download length mismatch")
                output.write(data)
            verify(partial, item)
            partial.chmod(0o644)
            os.link(partial, target)
        finally:
            if created:
                partial.unlink(missing_ok=True)
    print("Private legacy Miku model and runtime verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Private character model directory")
    download(parser.parse_args().directory)
