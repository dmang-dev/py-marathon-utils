"""M2 and Infinity integration tests.

Skipped unless MARATHON2_SAMPLE_DATA / MARATHON_INFINITY_SAMPLE_DATA env vars
point at the corresponding game data dirs (or the default local paths
resolve). See conftest.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from marathon_utils import macbinary, maps, sounds, wad

pytestmark = pytest.mark.needs_sample_data


# ---------------------------------------------------------------------------
# Marathon 2
# ---------------------------------------------------------------------------

def test_m2_map_is_macbinary_wrapped_v2_wad(m2_map: Path):
    blob = m2_map.read_bytes()
    data, _rsrc, meta = macbinary.unwrap(blob)
    assert data is not None
    assert meta["file_type"] == "sce2"

    hdr = wad.read_header(data)
    assert hdr["version"] == 2
    assert hdr["wad_count"] == 41
    assert hdr["entry_header_size"] == 16  # M2/Infinity chunk header
    assert hdr["dir_entry_size"] == 84     # M2 directory has 64-byte name


def test_m2_extract_maps(m2_map: Path, tmp_path: Path):
    result = maps.extract(m2_map, tmp_path / "Maps")
    assert result["level_count"] == 41
    # M2 levels have well-known names
    names = {lev["name"] for lev in result["levels"]}
    assert "Waterloo Waterpark" in names


def test_m2_lite_uses_function_block_format(m2_map: Path, tmp_path: Path):
    """M2 LITE records use the 100-byte multi-function-block layout, not the
    32-byte M1 layout. A parser stuck on M1 would silently produce garbage."""
    maps.extract(m2_map, tmp_path / "Maps")
    lev0 = next((tmp_path / "Maps").glob("00_*.json"))
    j = json.loads(lev0.read_text(encoding="utf-8"))
    lite = j["data"]["LITE"]
    assert len(lite) > 0
    # M2 light has a `functions` dict; M1 has `min_intensity/max_intensity` etc.
    assert "functions" in lite[0]
    assert "primary_active" in lite[0]["functions"]
    pa = lite[0]["functions"]["primary_active"]
    assert {"function", "period", "delta_period", "intensity", "delta_intensity"} <= set(pa)


def test_m2_extract_sounds_snd2(m2_sounds: Path, tmp_path: Path):
    result = sounds.extract(m2_sounds, tmp_path / "Sounds")
    assert result["format"] == "snd2"
    assert result["count"] >= 400  # ~487 in M2A1
    assert len(result["errors"]) == 0
    # Spot-check a WAV
    wav = next((tmp_path / "Sounds").rglob("*.wav"))
    head = wav.read_bytes()[:12]
    assert head[:4] == b"RIFF"
    assert head[8:12] == b"WAVE"


def test_m2_extract_shapes(m2_shapes: Path, tmp_path: Path):
    pytest.importorskip("PIL")
    from marathon_utils import shapes
    result = shapes.extract(m2_shapes, tmp_path / "Shapes")
    assert result["format_version"] == 2
    assert len(result["collections"]) >= 25
    assert len(result["errors"]) == 0


def test_m2_visualize(m2_map: Path, tmp_path: Path):
    pytest.importorskip("PIL")
    from marathon_utils import visualize
    result = visualize.render_all_levels(m2_map, tmp_path / "Maps")
    assert result["count"] == 41


# ---------------------------------------------------------------------------
# Marathon Infinity
# ---------------------------------------------------------------------------

def test_mi_map_is_macbinary_wrapped_v4_wad(mi_map: Path):
    blob = mi_map.read_bytes()
    data, _rsrc, _meta = macbinary.unwrap(blob)
    assert data is not None
    hdr = wad.read_header(data)
    assert hdr["version"] == 4    # Infinity bumped the WAD version
    assert hdr["wad_count"] == 57


def test_mi_levels_have_embedded_physics(mi_map: Path, tmp_path: Path):
    """Infinity ships per-level physics chunks (MNpx/FXpx/PRpx/PXpx/WPpx)."""
    maps.extract(mi_map, tmp_path / "Maps")
    lev0 = next((tmp_path / "Maps").glob("00_*.json"))
    j = json.loads(lev0.read_text(encoding="utf-8"))
    # Chunk sizes will list these tags even if we don't fully decode them
    chunks = j["chunk_sizes"]
    physics_chunks = {"MNpx", "FXpx", "PRpx", "PXpx", "WPpx"}
    assert physics_chunks <= set(chunks), \
        f"missing Infinity physics chunks: {physics_chunks - set(chunks)}"


def test_mi_extract_sounds(mi_sounds: Path, tmp_path: Path):
    result = sounds.extract(mi_sounds, tmp_path / "Sounds")
    assert result["format"] == "snd2"
    assert result["count"] >= 500  # ~583 in Infinity
    assert len(result["errors"]) == 0


def test_mi_extract_shapes(mi_shapes: Path, tmp_path: Path):
    pytest.importorskip("PIL")
    from marathon_utils import shapes
    result = shapes.extract(mi_shapes, tmp_path / "Shapes")
    assert result["format_version"] == 2
    assert len(result["collections"]) >= 30  # Infinity has more collections than M2


def test_mi_visualize(mi_map: Path, tmp_path: Path):
    pytest.importorskip("PIL")
    from marathon_utils import visualize
    result = visualize.render_all_levels(mi_map, tmp_path / "Maps")
    assert result["count"] == 57
