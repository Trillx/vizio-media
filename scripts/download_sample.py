"""Fetch the CC BY 3.0 trailer from Blender, verify it, then install it locally."""

import hashlib
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE = "https://download.blender.org/peach/trailer/trailer_iphone.m4v"
SHA256 = "2e09da35a9093921001a6f0a01fc544ba20a84588c4f9bc9a52b506888478280"
ROOT = Path(__file__).resolve().parents[1]


def verify(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest() == SHA256


def main():
    directory = Path(os.getenv("VIZIO_MEDIA_DIR",str(ROOT / "media")))
    directory.mkdir(parents=True,exist_ok=True)
    destination = directory / "sample.mp4"
    if verify(destination):
        print("Verified trailer already installed.")
        return
    partial = directory / "sample.part"
    try:
        request = Request(SOURCE, headers={"User-Agent": "VizioMedia-CompatibilityTest/0.1"})
        total = 0
        with urlopen(request, timeout=30) as response, partial.open("wb") as output:
            while chunk := response.read(65536):
                total += len(chunk)
                if total > 8 * 1024 * 1024:
                    raise ValueError("Unexpected media size; download stopped.")
                output.write(chunk)
        if not verify(partial):
            raise ValueError("Trailer checksum mismatch. The source may have changed; review before updating the checksum.")
        partial.replace(destination)
        print(f"Installed {total:,} bytes of verified H.264/AAC media: {destination}")
        print("(c) copyright 2008, Blender Foundation / www.bigbuckbunny.org. CC BY 3.0.")
    except Exception as error:
        partial.unlink(missing_ok=True)
        sys.exit(f"Could not install the test trailer: {error}")


if __name__ == "__main__":
    main()
