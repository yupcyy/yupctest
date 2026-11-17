#!/usr/bin/env python3
"""Download the pinned mcmeta assets used by the browser viewer."""
from pathlib import Path
from urllib.request import urlopen

ROOT = "https://raw.githubusercontent.com/misode/mcmeta"
FILES = (
    "1.20.1-summary/blocks/data.min.json",
    "1.20.1-summary/assets/block_definition/data.min.json",
    "1.20.1-summary/assets/model/data.min.json",
    "1.20.1-atlas/all/data.min.json",
    "1.20.1-atlas/all/atlas.png",
)
TARGET = Path(__file__).resolve().parents[2] / "building-viewer" / "public" / "mcmeta"


def main() -> None:
    for relative in FILES:
        destination = TARGET / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with urlopen(f"{ROOT}/{relative}", timeout=60) as response:
            content = response.read(32 * 1024 * 1024 + 1)
        if not content or len(content) > 32 * 1024 * 1024:
            raise RuntimeError(f"invalid resource size: {relative}")
        temporary.write_bytes(content)
        temporary.replace(destination)
        print(f"{relative}: {len(content)} bytes")


if __name__ == "__main__":
    main()
