"""Fetch pinned public Kokoro weights; the locked image supplies its Japanese dictionary."""

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path


def verify(path: Path, item: dict) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    if path.stat().st_size != item["size"] or digest.hexdigest() != item["sha256"]:
        raise ValueError(f"Checksum mismatch: {path.name}; refusing replacement")


def download(directory: Path) -> None:
    manifest = json.loads(Path(__file__).with_name("tts-model.json").read_text())
    new_directory = not directory.exists()
    directory.mkdir(parents=True, exist_ok=True, mode=0o755)
    if new_directory:
        directory.chmod(0o755)
    root = directory.resolve()
    for item in manifest["runtime_files"]:
        name = item["name"]
        if Path(name).name != name:
            raise ValueError("Expected plain file names")
        target = directory / name
        if not target.resolve().is_relative_to(root):
            raise ValueError("Model path leaves target directory")
        if target.exists():
            verify(target, item)
            continue
        partial = target.with_suffix(target.suffix + ".part")
        created = False
        try:
            with partial.open("xb") as output:
                created = True
                with urllib.request.urlopen(item["url"], timeout=90) as response:
                    received = 0
                    while chunk := response.read(1024 * 1024):
                        received += len(chunk)
                        if received > item["size"]:
                            raise ValueError("Download exceeds pinned length")
                        output.write(chunk)
            verify(partial, item)
            partial.chmod(0o644)
            os.link(partial, target)
        finally:
            if created:
                partial.unlink(missing_ok=True)

    print("Kokoro weights and voices verified; UniDic-lite is installed in the image")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Public model mount directory")
    download(parser.parse_args().directory)
