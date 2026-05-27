"""End-to-end integration tests that require a real Marathon-20250829 dir.

Skipped unless `MARATHON_SAMPLE_DATA` env var is set (or the default project
path is found). See conftest.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from marathon_utils import macbinary, maps, sounds, wad

pytestmark = pytest.mark.needs_sample_data


def test_map_scen_is_macbinary_wrapped_m1_wad(map_scen: Path):
    blob = map_scen.read_bytes()
    data, _rsrc, meta = macbinary.unwrap(blob)
    assert data is not None
    assert meta["file_type"] == "scen"

    hdr = wad.read_header(data)
    assert hdr["version"] == 0           # M1 WAD
    assert hdr["wad_count"] == 37        # M1A1 release scenario
    assert hdr["name"] == "Map"


def test_extract_maps_produces_37_levels(map_scen: Path, tmp_path: Path):
    result = maps.extract(map_scen, tmp_path / "Maps")
    assert result["level_count"] == 37
    assert any(lev["name"] == "Arrival" for lev in result["levels"])


def test_arrival_geometry_sanity(map_scen: Path, tmp_path: Path):
    """Spot-check that level 0 produces plausible geometry counts."""
    maps.extract(map_scen, tmp_path / "Maps")
    arrival = next((tmp_path / "Maps").glob("00_*.json"))
    import json
    j = json.loads(arrival.read_text())
    # Conservative sanity ranges — exact counts are validated by perl-parity test
    assert 200 <= len(j["data"]["POLY"]) <= 300
    assert 500 <= len(j["data"]["LINS"]) <= 1000
    assert 50 <= len(j["data"]["OBJS"]) <= 100
    # All polygons should have valid vertex counts
    for p in j["data"]["POLY"]:
        assert 0 <= p["vertex_count"] <= 8


def test_extract_sounds_produces_104_wavs(sounds_sndz: Path, tmp_path: Path):
    result = sounds.extract(sounds_sndz, tmp_path / "Sounds")
    assert result["count"] == 104
    assert len(result["errors"]) == 0
    # Spot-check a WAV file is RIFF-formatted
    sample = next((tmp_path / "Sounds").rglob("*.wav"))
    head = sample.read_bytes()[:12]
    assert head[:4] == b"RIFF"
    assert head[8:12] == b"WAVE"


def test_extract_shapes_loads_26_collections(shapes_shps: Path, tmp_path: Path):
    pytest.importorskip("PIL")
    from marathon_utils import shapes
    result = shapes.extract(shapes_shps, tmp_path / "Shapes")
    assert len(result["collections"]) == 26
    assert len(result["errors"]) == 0
    # Each collection should have at least a palette PNG
    for c in result["collections"]:
        assert (tmp_path / "Shapes" / f"Coll_{c['index']:02d}" / "palette.png").is_file()


def test_visualize_renders_37_levels(map_scen: Path, tmp_path: Path):
    pytest.importorskip("PIL")
    from marathon_utils import visualize
    result = visualize.render_all_levels(map_scen, tmp_path / "Maps", scale=0.05)
    assert result["count"] == 37
