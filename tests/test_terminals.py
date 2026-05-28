"""Unit + integration tests for the terminal renderer."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from marathon_utils import terminals


def test_split_lines_breaks_on_carriage_returns():
    runs = [{"text": "alpha\rbeta\rgamma", "font_index": 0, "underline": False, "color": 0}]
    out = terminals.split_lines(runs)
    assert len(out) == 3
    assert out[0][0]["text"] == "alpha"
    assert out[1][0]["text"] == "beta"
    assert out[2][0]["text"] == "gamma"


def test_split_lines_replaces_tabs_with_space():
    runs = [{"text": "a\tb\tc", "font_index": 0, "underline": False, "color": 0}]
    out = terminals.split_lines(runs)
    assert len(out) == 1
    assert out[0][0]["text"] == "a b c"


def test_wrap_line_monospace_greedy_break():
    runs = [{"text": "hello world foo bar baz", "font_index": 0,
             "underline": False, "color": 0}]
    out = terminals.wrap_line_monospace(runs, max_chars=11)
    # Greedy wrap at the last space within the first 11 chars
    assert len(out) >= 2
    flat = "".join("".join(r["text"] for r in line) for line in out)
    # Wrapped text should contain all the original chars (modulo leading-space trim)
    assert "hello" in flat and "world" in flat and "foo" in flat


def test_wrap_line_preserves_styles_across_break():
    runs = [
        {"text": "alpha ", "font_index": 0, "underline": False, "color": 0},
        {"text": "BETA gamma delta", "font_index": 1, "underline": False, "color": 1},
    ]
    out = terminals.wrap_line_monospace(runs, max_chars=8)
    # The "BETA" portion that spills onto a wrapped line should keep its style
    second_line_runs = out[1]
    assert any(r["font_index"] == 1 and r["color"] == 1 for r in second_line_runs)


def test_scrub_lines_drops_trailing_blanks():
    lines = [
        [{"text": "hello", "font_index": 0, "underline": False, "color": 0}],
        [{"text": "world", "font_index": 0, "underline": False, "color": 0}],
        [],
        [],
    ]
    out = terminals.scrub_lines(lines)
    assert len(out) == 2


@pytest.mark.needs_sample_data
def test_render_m2_terminals(m2_map: Path, tmp_path: Path):
    result = terminals.extract(m2_map, tmp_path / "Terminals")
    # M2 has 27 main levels with terminals (some bonus levels lack them)
    assert result["terminal_count"] >= 60
    assert result["page_count"] >= 300
    # Each page should be a real PNG
    samples = list((tmp_path / "Terminals").glob("0_s0u_p*.png"))
    assert samples, "expected at least one page for level 0 terminal 0"
    head = samples[0].read_bytes()[:8]
    assert head == b"\x89PNG\r\n\x1a\n"


@pytest.mark.needs_sample_data
def test_render_mi_terminals(mi_map: Path, tmp_path: Path):
    result = terminals.extract(mi_map, tmp_path / "Terminals")
    # Infinity has 57 levels, most with terminals
    assert result["terminal_count"] >= 60
