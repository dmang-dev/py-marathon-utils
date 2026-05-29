"""Tests for the M1 terminal compiler, location finder, HTML preview,
and the Samsara composer."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from marathon_utils import strings, terminals

# ---------------------------------------------------------------------------
# M1 terminal compiler
# ---------------------------------------------------------------------------

def test_compile_m1_script_recognizes_directives():
    script = (
        ";L000.WELCOME.ENTRY\n"
        "#logon\n"
        "Test logon screen\n"
        ";\n"
        "#information\n"
        "$BBold heading$b\n"
        "Body text continues here.\n"
        "#checkpoint 0\n"
        "Goal marker."
    )
    compiled = terminals.compile_m1_script(script)
    assert compiled["lines_per_page"] == 23
    type_names = [g["type_name"] for g in compiled["groupings"]]
    assert "logon" in type_names
    assert "information" in type_names
    assert "checkpoint" in type_names
    # Goal permutation captured from directive
    cp = next(g for g in compiled["groupings"] if g["type_name"] == "checkpoint")
    assert cp["permutation"] == 0


def test_compile_m1_inline_bold_emits_font_changes():
    script = "#information\nNormal $BBold$b normal."
    compiled = terminals.compile_m1_script(script)
    fc = compiled["font_changes"]
    # Should have at least one bold-on and one bold-off transition
    assert any(f["bold"] for f in fc)
    assert any(not f["bold"] for f in fc)


def test_compile_m1_status_modifier_emitted():
    script = (
        ";L010.SOMETHING.ENTRY\n#logon\nentry text\n"
        ";L010.SOMETHING.SUCCESS\n#logon\nsuccess text\n"
    )
    compiled = terminals.compile_m1_script(script)
    type_names = [g["type_name"] for g in compiled["groupings"]]
    assert "success" in type_names


@pytest.mark.needs_sample_data
def test_m1_arrival_compiles_and_renders(sample_dir: Path, tmp_path: Path):
    """The iconic Arrival opening terminal compiles + renders end-to-end."""
    appl = sample_dir / "Marathon.appl"
    if not appl.is_file():
        pytest.skip("Marathon.appl not found")
    r = strings.extract(appl)
    script = r["term"].get(1000)
    assert script and "Leela" in script
    compiled = terminals.compile_m1_script(script)
    assert any(g["type_name"] == "logon" for g in compiled["groupings"])
    fonts = terminals.load_default_fonts()
    pages = terminals.render_terminal(compiled, fonts=fonts, level_name="Arrival")
    assert len(pages) >= 2


# ---------------------------------------------------------------------------
# Terminal locations
# ---------------------------------------------------------------------------

@pytest.mark.needs_sample_data
def test_m2_terminal_locations_found(m2_map: Path):
    from marathon_utils import macbinary, maps, wad
    blob = m2_map.read_bytes()
    data, _r, _m = macbinary.unwrap(blob)
    hdr = wad.read_header(data)
    entry = wad.read_directory(data, hdr)[0]
    level = maps.parse_level(data, entry, hdr)
    locs = terminals.terminal_locations(level, is_m1=False)
    # M2 level 0 (Waterloo Waterpark) has 2 terminals
    assert len(locs) == 2
    for loc in locs:
        assert {"poly", "line", "x", "y", "panel_perm", "panel_type"} <= set(loc)


# ---------------------------------------------------------------------------
# HTML preview
# ---------------------------------------------------------------------------

def test_html_preview_generates_index(tmp_path: Path):
    # Create a few fake PNGs with the expected naming pattern
    for fname in ("0_s0u_p0.png", "0_s0u_p1.png", "1_s0u_p0.png"):
        (tmp_path / fname).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    path = terminals.generate_html_preview(tmp_path, scenario_name="Test")
    assert Path(path).is_file()
    html = Path(path).read_text(encoding="utf-8")
    assert "Test Terminals" in html
    assert "0_s0u_p0.png" in html
    assert "1_s0u_p0.png" in html


# ---------------------------------------------------------------------------
# Samsara composer
# ---------------------------------------------------------------------------

@pytest.mark.needs_sample_data
def test_samsara_composer_produces_marines(mi_shapes: Path, tmp_path: Path):
    """Full Samsara composite is slow; smoke-test the abbreviated mode."""
    from marathon_utils import samsara
    r = samsara.compose_marines(mi_shapes, tmp_path / "Samsara", full_animation=False)
    # 8 colors x 24 torsos x 5 legs x up to 8 views = ~7,680 in abbreviated mode
    assert r["count"] > 5000
    # Spot-check a known combination exists
    sample = next((tmp_path / "Samsara" / "green").rglob("view0.png"))
    head = sample.read_bytes()[:8]
    assert head == b"\x89PNG\r\n\x1a\n"
