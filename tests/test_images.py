"""Tests for the Images.imgA PICT v2 decoder."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from marathon_utils import images

# ---------------------------------------------------------------------------
# PackBits unit codec
# ---------------------------------------------------------------------------

def test_unpack_bits_literal_and_run_1byte():
    # 0x02 -> copy 3 literal bytes (AA BB CC); 0xFE -> repeat next byte 3x (DD)
    data = bytes([0x02, 0xAA, 0xBB, 0xCC, 0xFE, 0xDD])
    out, pos = images.unpack_bits(data, 0, n_units=6, unit_size=1)
    assert out == bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xDD, 0xDD])
    assert pos == len(data)


def test_unpack_bits_noop_byte_ignored():
    # 0x80 is a no-op; then copy 1 literal byte
    data = bytes([0x80, 0x00, 0x11])
    out, _ = images.unpack_bits(data, 0, n_units=1, unit_size=1)
    assert out == bytes([0x11])


def test_unpack_bits_2byte_units():
    # repeat a 16-bit unit (0x1234) twice, then one literal unit (0x5678)
    data = bytes([0xFF, 0x12, 0x34, 0x00, 0x56, 0x78])
    out, _ = images.unpack_bits(data, 0, n_units=3, unit_size=2)
    assert out == bytes([0x12, 0x34, 0x12, 0x34, 0x56, 0x78])


# ---------------------------------------------------------------------------
# Full decode against real data
# ---------------------------------------------------------------------------

@pytest.mark.needs_sample_data
def test_m2_images_all_decode(m2_dir: Path, tmp_path: Path):
    src = m2_dir / "Images.imgA"
    if not src.is_file():
        pytest.skip("Images.imgA not found")
    result = images.extract(src, tmp_path / "Images")
    # M2 ships 14 PICTs; all should decode with no errors
    assert result["count"] == 14
    assert result["errors"] == []
    # Title screen is 640x480 (8-bit indexed) and a 32-bit direct variant exists
    sizes = {(im["width"], im["height"]) for im in result["images"]}
    assert (640, 480) in sizes
    assert (640, 160) in sizes  # the title banner


@pytest.mark.needs_sample_data
def test_mi_images_all_decode(mi_dir: Path, tmp_path: Path):
    src = mi_dir / "Images.imgA"
    if not src.is_file():
        pytest.skip("Images.imgA not found")
    result = images.extract(src, tmp_path / "Images")
    assert result["count"] == 17
    assert result["errors"] == []


@pytest.mark.needs_sample_data
def test_decode_pict_returns_rgb_image(m2_dir: Path):
    """The indexed title screen (PICT 1000) decodes to a 640x480 RGB image."""
    from marathon_utils import macbinary, macrsrc
    src = m2_dir / "Images.imgA"
    if not src.is_file():
        pytest.skip("Images.imgA not found")
    _d, rsrc, _m = macbinary.unwrap(src.read_bytes())
    pict = next(e for e in macrsrc.parse(rsrc)["PICT"] if e["id"] == 1000)
    img = images.decode_pict(pict["data"])
    assert img.mode == "RGB"
    assert img.size == (640, 480)
    # Not a blank image — the Durandal logo has non-black pixels
    assert any(b != 0 for b in img.tobytes())
