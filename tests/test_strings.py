"""Unit and integration tests for the strings module."""
from __future__ import annotations

from pathlib import Path

import pytest

from marathon_utils import strings

# ---------------------------------------------------------------------------
# Unit tests — crafted minimal inputs
# ---------------------------------------------------------------------------

def test_parse_str_single():
    # Pascal-style: length byte, then bytes
    payload = bytes([5]) + b"Hello"
    assert strings.parse_str(payload) == "Hello"


def test_parse_strs_indexed_list():
    # uint16 count, then Pascal strings
    payload = b"\x00\x03" + bytes([3]) + b"foo" + bytes([5]) + b"hello" + bytes([0])
    out = strings.parse_strs(payload)
    assert out == ["foo", "hello", ""]


def test_parse_text_returns_full_payload():
    payload = b"some long text body with newlines\nand stuff"
    assert strings.parse_text(payload) == "some long text body with newlines\nand stuff"


def test_parse_m1_terminal_resource_normalizes_line_endings():
    # M1 uses classic Mac \r line endings; we normalize to \n
    payload = b";L000.WELCOME\r#logon\rsome text\r"
    out = strings.parse_m1_terminal_resource(payload)
    assert "\r" not in out
    assert out.split("\n")[0] == ";L000.WELCOME"


# ---------------------------------------------------------------------------
# Integration test — Marathon.appl
# ---------------------------------------------------------------------------

pytestmark_int = pytest.mark.needs_sample_data


def test_parse_clut_decodes_color_entries():
    import struct
    # 6 bytes skip + uint16 count_minus_1 + entries (2 pad + 6 RGB each)
    payload = b"\x00" * 6 + struct.pack(">H", 1)  # count = 2
    payload += b"\x00\x00" + struct.pack(">HHH", 0xFFFF, 0, 0)         # red
    payload += b"\x00\x00" + struct.pack(">HHH", 0, 0xFFFF, 0)         # green
    colors = strings.parse_clut(payload)
    assert len(colors) == 2
    assert colors[0]["red"] == 1.0 and colors[0]["green"] == 0.0
    assert colors[1]["green"] == 1.0


def test_parse_nrct_decodes_rectangle_entries():
    import struct
    payload = struct.pack(">H", 2)  # count
    payload += struct.pack(">hhhh", 10, 20, 30, 40)
    payload += struct.pack(">hhhh", -5, -10, -15, -20)
    rects = strings.parse_nrct(payload)
    assert rects == [
        {"index": 0, "top": 10, "left": 20, "bottom": 30, "right": 40},
        {"index": 1, "top": -5, "left": -10, "bottom": -15, "right": -20},
    ]


def test_parse_finf_decodes_font_entries():
    import struct
    payload = struct.pack(">H", 2)  # count
    payload += struct.pack(">HHH", 4, 0, 12)
    payload += struct.pack(">HHH", 22, 1, 14)
    fonts = strings.parse_finf(payload)
    assert fonts == [
        {"index": 0, "file": "#4", "style": 0, "size": 12},
        {"index": 1, "file": "#22", "style": 1, "size": 14},
    ]


def test_to_mml_emits_interface_and_stringsets():
    extracted = {
        "interface": {
            "color": [{"index": 0, "red": 1.0, "green": 0.0, "blue": 0.0}],
            "rect": [{"index": 5, "top": 1, "left": 2, "bottom": 3, "right": 4}],
            "font": [{"index": 0, "file": "#4", "style": 0, "size": 12}],
        },
        "STR#": {128: ["hello", "world"]},
    }
    mml = strings.to_mml(extracted)
    assert "<interface>" in mml
    assert "<color " in mml
    assert "<rect " in mml
    assert "<font " in mml
    assert '<stringset index="128">' in mml
    assert "<string index=\"0\">hello</string>" in mml


@pytest.mark.needs_sample_data
def test_m1_marathon_appl_strings_and_terminals(sample_dir: Path, tmp_path: Path):
    appl = sample_dir / "Marathon.appl"
    if not appl.is_file():
        pytest.skip("Marathon.appl not found in sample dir")
    result = strings.extract(appl, tmp_path / "AppStrings")

    # Should have multiple STR# sets and the iconic resource-fork easter egg
    assert len(result["STR#"]) >= 10
    assert any("looking through my resource fork" in t for t in result["TEXT"].values())

    # 62 term resources include the Arrival opening — the Leela welcome line
    assert 1000 in result["term"]
    arrival = result["term"][1000]
    assert "L000" in arrival
    assert "Leela" in arrival
