"""Round-trip tests for shapes.write_m2."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from marathon_utils import shapes


@pytest.mark.needs_sample_data
def test_m2_shapes_round_trip_image_perfect(m2_shapes: Path):
    """Parse M2 Shapes.shpA, write it back, re-parse — rendered images identical.

    We compare via `to_image()` rather than raw `.indices` because the writer
    legitimately normalizes column-major raw bitmaps to row-major storage; that
    changes the byte order of `.indices` but produces a pixel-identical image.
    """
    blob = m2_shapes.read_bytes()
    c1 = shapes.parse_m2_collections(blob)
    assert len(c1) >= 25

    re_emitted = shapes.write_m2(c1)
    c2 = shapes.parse_m2_collections(re_emitted)
    assert len(c2) == len(c1)

    for a, b in zip(c1, c2):
        assert a["index"] == b["index"]
        assert len(a["bitmaps"]) == len(b["bitmaps"])
        palette = a["cluts"][0] if a["cluts"] else [(0, 0, 0)] * 256
        for bm_a, bm_b in zip(a["bitmaps"], b["bitmaps"]):
            assert bm_a.width == bm_b.width
            assert bm_a.height == bm_b.height
            # Pixel-identical after rendering (orientation-independent)
            assert bm_a.to_image(palette).tobytes() == bm_b.to_image(palette).tobytes()


@pytest.mark.needs_sample_data
def test_m2_shapes_round_trip_preserves_both_banks(m2_shapes: Path):
    """The writer round-trips the 16-bit shape bank as well as the 8-bit bank."""
    blob = m2_shapes.read_bytes()
    c1 = shapes.parse_m2_collections(blob, include_16bit=True)
    banks16 = [c for c in c1 if c["bit_depth"] == 16]
    assert banks16, "expected at least one 16-bit collection bank in M2 shapes"

    c2 = shapes.parse_m2_collections(shapes.write_m2(c1), include_16bit=True)
    # Same count of 8-bit and 16-bit entries survive the round-trip
    assert sum(c["bit_depth"] == 8 for c in c1) == sum(c["bit_depth"] == 8 for c in c2)
    assert sum(c["bit_depth"] == 16 for c in c1) == sum(c["bit_depth"] == 16 for c in c2)
    # 16-bit banks carry a fuller palette (256 vs the 8-bit bank's 224)
    assert any(c["header"]["color_count"] == 256 for c in banks16)


@pytest.mark.needs_sample_data
def test_m2_collections_8bit_only_flag(m2_shapes: Path):
    """`include_16bit=False` yields exactly one entry per populated slot."""
    blob = m2_shapes.read_bytes()
    only8 = shapes.parse_m2_collections(blob, include_16bit=False)
    assert all(c["bit_depth"] == 8 for c in only8)
    # one entry per unique index
    assert len({c["index"] for c in only8}) == len(only8)


@pytest.mark.needs_sample_data
def test_mi_shapes_round_trip(mi_shapes: Path):
    """Same for Infinity — its 32-collection table is denser."""
    blob = mi_shapes.read_bytes()
    c1 = shapes.parse_m2_collections(blob)
    re_emitted = shapes.write_m2(c1)
    c2 = shapes.parse_m2_collections(re_emitted)
    assert len(c2) == len(c1)
    # Spot-check the marine collection (6) which Samsara consumes
    marine_a = next((c for c in c1 if c["index"] == 6), None)
    marine_b = next((c for c in c2 if c["index"] == 6), None)
    if marine_a and marine_b:
        assert len(marine_a["bitmaps"]) == len(marine_b["bitmaps"])
        assert len(marine_a["high_shapes"]) == len(marine_b["high_shapes"])
