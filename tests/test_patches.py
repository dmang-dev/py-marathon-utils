"""Tests for the Anvil patch reader and applier.

We don't bundle real community patches (different licensing) so these tests
build synthetic minimal patches from scratch and verify round-trips.
"""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

pytest.importorskip("PIL")  # patches.parse uses shapes which needs Pillow

from marathon_utils import patches


def _build_minimal_patch_with_bitmap() -> bytes:
    """Hand-construct a patch with one collection containing one tiny raw bitmap."""
    # Per-collection header: index=5, bit_depth=8
    out = bytearray()
    out += struct.pack(">II", 5, 8)

    # bmap chunk: tag + int32 index + int32 size + bitmap header + data
    out += b"bmap"
    out += struct.pack(">i", 12)             # bitmap index
    out += struct.pack(">i", 0)              # size (unused by reader)
    # Bitmap header: width=4, height=3, bytes_per_row=4, flags=0, depth=8, reserved
    out += struct.pack(">hhhHh", 4, 3, 4, 0, 8)
    out += b"\x00" * 16                       # reserved bytes
    # Address table for row-order raw bitmap: (height+1) int32s
    out += b"\x00" * (4 * (3 + 1))
    # Raw pixel data: 4 * 3 = 12 bytes
    out += bytes([1, 2, 3, 4,  5, 6, 7, 8,  9, 10, 11, 12])

    # endc terminator
    out += b"endc"
    return bytes(out)


def test_parse_minimal_patch_with_one_bitmap():
    blob = _build_minimal_patch_with_bitmap()
    patch = patches.parse(blob)
    assert len(patch["collections"]) == 1
    coll = patch["collections"][0]
    assert coll["index"] == 5
    assert coll["bit_depth"] == 8
    assert len(coll["bitmaps"]) == 1
    entry = coll["bitmaps"][0]
    assert entry["index"] == 12
    assert entry["bitmap"].width == 4
    assert entry["bitmap"].height == 3
    # First pixel of the decoded 4x3 raw bitmap should be 1
    assert entry["bitmap"].indices[0] == 1
    assert entry["bitmap"].indices[-1] == 12


def test_apply_replaces_bitmaps_in_target_collection():
    from marathon_utils import shapes

    blob = _build_minimal_patch_with_bitmap()
    patch = patches.parse(blob)

    # Build a synthetic "base" collection with 14 bitmap slots, none equal to
    # the patch's bitmap; apply should overwrite slot 12 only.
    placeholder = shapes.Bitmap(1, 1, 0, b"\x00")
    base = {
        5: {
            "header": {},
            "cluts": [[(0, 0, 0)] * 256],
            "bitmaps": [placeholder for _ in range(14)],
            "high_shapes": [],
            "low_shapes": [],
        }
    }
    result = patches.apply(base, patch)
    assert 5 in result["collections"]
    patched_coll = result["collections"][5]
    # All bitmaps except slot 12 should still be the placeholder
    assert patched_coll["bitmaps"][11] is placeholder
    assert patched_coll["bitmaps"][13] is placeholder
    # Slot 12 replaced
    new_bm = patched_coll["bitmaps"][12]
    assert new_bm.width == 4 and new_bm.height == 3
    assert result["summary"]["details"][0]["bitmaps_replaced"] == [12]


def test_apply_skips_collections_not_in_base():
    blob = _build_minimal_patch_with_bitmap()  # patches collection 5
    patch = patches.parse(blob)

    base = {99: {"header": {}, "bitmaps": [], "cluts": [],
                 "high_shapes": [], "low_shapes": []}}
    result = patches.apply(base, patch)
    assert result["summary"]["collections_touched"] == []
    assert result["summary"]["details"][0]["skipped"] == "not in base"


def test_real_world_ctf_flag_patch():
    """Cross-check against a real community patch from Simplici7y.

    Source: https://simplici7y.com/items/ctf-flag-shapes-patch-4/
    Format: Anvil patch — replaces items[14] and items[15] with bigger CTF flags.
    The .zip with the patch is bundled in sample-data/ for offline testing.
    """
    import zipfile
    zip_path = Path(__file__).resolve().parent.parent / "sample-data" / "CTF_Flag_Shapes_Patch.zip"
    if not zip_path.is_file():
        pytest.skip(f"CTF flag patch not bundled at {zip_path}")
    blob = zipfile.ZipFile(zip_path).read("CTF Flag Shapes Patch")
    result = patches.parse(blob)

    # 37 collection slots in the patch, 36 are empty placeholders
    assert len(result["collections"]) == 37
    non_empty = [c for c in result["collections"]
                 if c["definition"] or c["bitmaps"]]
    assert len(non_empty) == 1

    coll = non_empty[0]
    assert coll["index"] == 7        # M2/Infinity "Items" collection
    assert coll["bit_depth"] == 8
    assert coll["definition"] is not None
    # Two replacement bitmaps — the red flag and the blue flag
    assert len(coll["bitmaps"]) == 2
    assert {b["index"] for b in coll["bitmaps"]} == {14, 15}
    for b in coll["bitmaps"]:
        assert b["bitmap"].width == 67
        assert b["bitmap"].height == 148
        # Real sprite — should have meaningful opaque pixels (~25% per visual check)
        nonzero = sum(1 for px in b["bitmap"].indices if px != 0)
        assert nonzero > 1000


def test_parse_color_table_after_cldf():
    """ctab follows cldf so the parser knows color_count."""
    out = bytearray()
    out += struct.pack(">II", 0, 8)  # collection 0, depth 8
    # cldf with color_count = 4. Payload is 544 B (38 fields + 506 padding).
    out += b"cldf"
    cldf = bytearray(544)
    # collection header: version, type, flags, color_count, clut_count
    struct.pack_into(">hhHhh", cldf, 0, 0, 0, 0, 4, 1)
    out += bytes(cldf)
    # ctab: int32 index, then 4 colors of 8 bytes
    out += b"ctab"
    out += struct.pack(">i", 0)  # color table index
    for i, (r, g, b) in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255), (200, 200, 200)]):
        out += struct.pack(">BBHHH", 0, i, r << 8, g << 8, b << 8)
    out += b"endc"

    patch = patches.parse(bytes(out))
    coll = patch["collections"][0]
    assert coll["definition"]["color_count"] == 4
    assert len(coll["color_tables"]) == 1
    assert coll["color_tables"][0]["colors"][0] == {
        "self_luminescent": False, "value": 0,
        "r": 255, "g": 0, "b": 0,
    }
