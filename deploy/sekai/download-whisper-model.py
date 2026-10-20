"""Download and verify the pinned public Whisper weights before offline deployment."""

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path


def verify(path: Path, expected_size: int, expected_hash: str) -> None:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    if size != expected_size or digest.hexdigest() != expected_hash:
        raise ValueError(f"Hash/size mismatch for {path.name}; not replacing existing data")


def download(directory: Path) -> None:
    manifest = json.loads(Path(__file__).with_name("whisper-model.json").read_text())
    new_directory = not directory.exists()
    directory.mkdir(parents=True, exist_ok=True, mode=0o755)
    if new_directory:
        # The model is public; the non-root container must traverse its mount root.
        directory.chmod(0o755)
    for item in manifest["files"]:
        name, size, expected_hash = item["name"], item["size"], item["sha256"]
        if Path(name).name != name:
            raise ValueError("The manifest must contain plain file names")
        target = directory / name
        if target.exists():
            verify(target, size, expected_hash)
            print(f"Verified existing {name}", flush=True)
            continue
        url = (
            f"https://huggingface.co/{manifest['repository']}/resolve/"
            f"{manifest['revision']}/{name}?download=true"
        )
        partial = target.with_name(name + ".part")
        created = False
        try:
            with partial.open("xb") as output:
                created = True
                with urllib.request.urlopen(url, timeout=60) as response:
                    received = 0
                    while chunk := response.read(1024 * 1024):
                        received += len(chunk)
                        if received > size:
                            raise ValueError("Download exceeds the pinned size")
                        output.write(chunk)
            verify(partial, size, expected_hash)
            # Hard-link creation is atomic and refuses an existing target.
            os.link(partial, target)
            target.chmod(0o644)
        finally:
            if created:
                partial.unlink(missing_ok=True)
        print(f"Downloaded and verified {name}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory", type=Path, help="Public model directory to mount read-only"
    )
    download(parser.parse_args().directory)
