"""Unit and integration tests for the physics module."""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

from marathon_utils import physics

# ---------------------------------------------------------------------------
# Unit tests — crafted minimal inputs
# ---------------------------------------------------------------------------

def test_fxpx_record_size_constant():
    assert physics.FXPX_RECORD == 14


def test_prpx_record_size_constant():
    assert physics.PRPX_RECORD == 48


def test_mnpx_record_size_constant():
    assert physics.MNPX_RECORD == 156


def test_pxpx_record_size_constant():
    assert physics.PXPX_RECORD == 104


def test_wppx_record_size_constant():
    assert physics.WPPX_RECORD == 134


def test_parse_fxpx_record_decodes_simple_fields():
    data = bytearray(physics.FXPX_RECORD)
    struct.pack_into(">hhiHhh", data, 0,
                     12,          # collection
                     5,           # shape
                     0x00010000,  # sound_pitch (Fixed) = 1.0
                     0x0001,      # flags
                     30,          # delay
                     400)         # delay_sound
    out = physics.parse_fxpx_record(bytes(data), 0)
    assert out == {
        "collection": 12,
        "shape": 5,
        "sound_pitch": 1.0,
        "flags": 1,
        "delay": 30,
        "delay_sound": 400,
    }


def test_decode_chunk_returns_none_for_unknown_tag():
    assert physics.decode_chunk("XXXX", b"") is None


def test_decode_chunk_iterates_records():
    # Two zero-filled FXpx records — all fields decode to 0.0/0
    data = bytes(physics.FXPX_RECORD * 2)
    out = physics.decode_chunk("FXpx", data)
    assert out is not None
    assert len(out) == 2
    assert all(rec["collection"] == 0 for rec in out)


# ---------------------------------------------------------------------------
# Integration tests — real .phyA + embedded chunks
# ---------------------------------------------------------------------------

@pytest.mark.needs_sample_data
def test_m2_standard_phya_decodes_to_expected_counts(m2_dir: Path, tmp_path: Path):
    src = m2_dir / "Physics Models" / "Standard.phyA"
    if not src.is_file():
        pytest.skip(f"Standard.phyA not found in {src.parent}")
    result = physics.extract(src, tmp_path / "Physics")
    assert result["wad_header"]["version"] == 2
    # M2 ships 43/67/38/2/9 records
    assert result["chunks"] == {
        "monsters": 43, "effects": 67, "projectiles": 38,
        "physics_constants": 2, "weapons": 9,
    }


@pytest.mark.needs_sample_data
def test_mi_standard_phya_matches_m2_counts(mi_dir: Path, tmp_path: Path):
    """Aleph One ships the same Standard.phyA for M2 and Infinity (the per-level
    embedded chunks are what makes Infinity special)."""
    src = mi_dir / "Physics Models" / "Standard.phyA"
    if not src.is_file():
        pytest.skip(f"Standard.phyA not found in {src.parent}")
    result = physics.extract(src, tmp_path / "Physics")
    assert result["chunks"]["monsters"] == 43


@pytest.mark.needs_sample_data
def test_mi_level_embedded_physics_decoded(mi_map: Path, tmp_path: Path):
    """MI levels embed per-level physics that should decode via maps.parse_level."""
    from marathon_utils import macbinary, maps, wad

    blob = mi_map.read_bytes()
    data, _r, _m = macbinary.unwrap(blob)
    hdr = wad.read_header(data)
    entry = wad.read_directory(data, hdr)[0]
    level = maps.parse_level(data, entry, hdr)

    emb = level["data"].get("embedded_physics")
    assert emb is not None
    assert {"monsters", "effects", "projectiles",
            "physics_constants", "weapons"} <= set(emb)
    # First monster should look sane
    m0 = emb["monsters"][0]
    assert m0["vitality"] > 0
    assert 0 < m0["radius"] < 10  # WU range — way too big = wrong endianness


@pytest.mark.needs_sample_data
def test_m1_physics_phys_falls_back_gracefully(sample_dir: Path, tmp_path: Path):
    """M1 Physics.phys uses an older layout — extractor should preserve raw bytes."""
    src = sample_dir / "Physics.phys"
    if not src.is_file():
        pytest.skip("Physics.phys not found")
    result = physics.extract(src, tmp_path / "Physics")
    assert result["wad_header"] is None
    assert (tmp_path / "Physics" / "Physics.raw").is_file()
