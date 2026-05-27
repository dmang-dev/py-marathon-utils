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
