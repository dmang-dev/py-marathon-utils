"""Download community Anvil patches from Simplici7y for tests + examples.

These are third-party files we don't redistribute in the repo. Run this script
once after cloning to populate `sample-data/` so the patches test suite (and
the example below) can run against real-world data.

Usage:
    python scripts/fetch_sample_patches.py
"""
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEST = REPO_ROOT / "sample-data"

# (filename, source URL, description)
PATCHES = [
    (
        "CTF_Flag_Shapes_Patch.zip",
        "https://simplici7y.com/items/ctf-flag-shapes-patch-4/downloads/new",
        "CTF Flag Shapes Patch by Juice — replaces items[14] and items[15] "
        "with 67x148 flag sprites. Two-collection Anvil patch.",
    ),
]


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    print(f"Fetching test fixtures into {DEST}")
    print()

    for filename, url, desc in PATCHES:
        target = DEST / filename
        if target.is_file():
            print(f"  [skip] {filename} already present ({target.stat().st_size:,} bytes)")
            continue
        print(f"  [get]  {filename}")
        print(f"         {desc}")
        try:
            urllib.request.urlretrieve(url, target)
        except Exception as e:
            print(f"         ERROR: {e}")
            return 1
        print(f"         {target.stat().st_size:,} bytes")

    print()
    print("Done. Run `pytest` and the patches tests will now find these fixtures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
