"""Round-trip tests for the patches writer.

`patches.write(patches.parse(blob)) == patches.parse(blob)` is the key
guarantee: the bytes we emit re-parse to a dict identical to the original.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

pytest.importorskip("PIL")

from marathon_utils import patches


def _bitmaps_equal(a, b) -> bool:
    return (a.width == b.width and a.height == b.height
            and a.indices == b.indices)


def test_patches_round_trip_synthetic():
    """Build a synthetic patch, write, parse, write again — confirms stable bytes."""
    from marathon_utils import shapes

    # Build a minimal patch dict with one collection containing one tiny bitmap
    bm = shapes.Bitmap(4, 3, 0, bytes([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]))
    patch = {
        "collections": [{
            "index": 7,
            "bit_depth": 8,
            "definition": None,
            "color_tables": [],
            "high_shapes": [],
            "low_shapes": [],
            "bitmaps": [{"index": 0, "bitmap": bm}],
        }]
    }
    blob1 = patches.write(patch)
    blob2 = patches.write(patches.parse(blob1))
    assert blob1 == blob2


def test_patches_round_trip_real_ctf_patch():
    """The real CTF Flag patch from Simplici7y must survive parse/write/parse
    with identical bitmap pixels."""
    zip_path = Path(__file__).resolve().parent.parent / "sample-data" / "CTF_Flag_Shapes_Patch.zip"
    if not zip_path.is_file():
        pytest.skip(f"CTF flag patch not bundled at {zip_path}")

    orig_blob = zipfile.ZipFile(zip_path).read("CTF Flag Shapes Patch")
    p1 = patches.parse(orig_blob)
    re_emitted = patches.write(p1)
    p2 = patches.parse(re_emitted)

    # Collection counts match
    assert len(p1["collections"]) == len(p2["collections"])
    # Find the one non-empty collection
    c1 = next(c for c in p1["collections"] if c["bitmaps"])
    c2 = next(c for c in p2["collections"] if c["bitmaps"])
    assert c1["index"] == c2["index"]
    assert c1["bit_depth"] == c2["bit_depth"]
    assert len(c1["bitmaps"]) == len(c2["bitmaps"])
    for b1, b2 in zip(c1["bitmaps"], c2["bitmaps"]):
        assert b1["index"] == b2["index"]
        assert _bitmaps_equal(b1["bitmap"], b2["bitmap"])


def test_patches_apply_after_round_trip():
    """An applied round-tripped patch yields the same modifications."""
    zip_path = Path(__file__).resolve().parent.parent / "sample-data" / "CTF_Flag_Shapes_Patch.zip"
    if not zip_path.is_file():
        pytest.skip(f"CTF flag patch not bundled at {zip_path}")

    from marathon_utils import shapes

    orig_blob = zipfile.ZipFile(zip_path).read("CTF Flag Shapes Patch")
    patch = patches.parse(patches.write(patches.parse(orig_blob)))

    placeholder = shapes.Bitmap(1, 1, 0, b"\x00")
    base = {7: {"header": {}, "cluts": [], "bitmaps": [placeholder] * 16,
                "high_shapes": [], "low_shapes": []}}
    result = patches.apply(base, patch)
    new_bitmaps = result["collections"][7]["bitmaps"]
    assert new_bitmaps[14].width == 67
    assert new_bitmaps[15].width == 67
