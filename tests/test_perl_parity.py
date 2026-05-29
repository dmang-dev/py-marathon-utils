"""Compare our Map.scen parser against the upstream marathon-utils Perl.

This is the strongest correctness guarantee for the maps module. We feed the
MacBinary-unwrapped data fork to `map2xml.pl`, parse the resulting XML, and
compare key per-record fields against our JSON output.

Skipped if Perl is not on PATH, XML::Writer is not findable, or
`MARATHON_SAMPLE_DATA` is not set.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from marathon_utils import macbinary, maps

pytestmark = pytest.mark.needs_sample_data


def _perl_lib() -> Path | None:
    """Locate a vendored XML::Writer path if present."""
    repo = Path(__file__).resolve().parents[1]
    candidates = [repo / "vendor" / "perl-lib"]
    for c in candidates:
        if (c / "XML" / "Writer.pm").is_file():
            return c
    return None


def _have_perl_with_xml_writer() -> bool:
    if shutil.which("perl") is None:
        return False
    args = ["perl"]
    lib = _perl_lib()
    if lib is not None:
        args += ["-I", str(lib)]
    args += ["-MXML::Writer", "-e", "1"]
    r = subprocess.run(args, capture_output=True, text=True)
    return r.returncode == 0


def _find_map2xml() -> Path | None:
    """Locate a local marathon-utils checkout for the cross-validation test.

    The upstream Perl is not vendored in this repo (it's third-party and
    unlicensed). Point `MARATHON_UTILS_DIR` at a local clone of
    https://github.com/Hopper262/marathon-utils to enable the parity test;
    otherwise it skips.
    """
    import os
    env = os.environ.get("MARATHON_UTILS_DIR")
    candidates = []
    if env:
        candidates.append(Path(env) / "map2xml.pl")
    # A sibling clone, if present.
    candidates.append(Path(__file__).resolve().parents[2] / "marathon-utils" / "map2xml.pl")
    for c in candidates:
        if c.is_file():
            return c
    return None


def _shape_desc(clut: int, coll: int, shape: int) -> int:
    if coll == -1:
        return 0xFFFF
    return (clut << 13) | (coll << 8) | (shape & 0xFF)


def _perl_attrs(xml: str, tag: str, index: int) -> dict | None:
    m = re.search(rf'<{tag} index="{index}"[^/]*/>', xml)
    if not m:
        return None
    return dict(re.findall(r'(\w+)="([^"]*)"', m.group(0)))


def test_python_matches_perl(map_scen: Path, tmp_path: Path):
    if not _have_perl_with_xml_writer():
        pytest.skip("perl + XML::Writer required for parity test")
    map2xml = _find_map2xml()
    if map2xml is None:
        pytest.skip("vendor/marathon-utils/map2xml.pl not available")

    # Unwrap MacBinary and feed data fork to map2xml
    data, _r, _m = macbinary.unwrap(map_scen.read_bytes())
    with tempfile.NamedTemporaryFile(delete=False, suffix=".datafork") as tf:
        tf.write(data)
        fork = tf.name

    perl_cmd = ["perl"]
    lib = _perl_lib()
    if lib is not None:
        perl_cmd += ["-I", str(lib)]
    perl_cmd.append(str(map2xml))

    with open(fork, "rb") as stdin_fp:
        result = subprocess.run(
            perl_cmd,
            stdin=stdin_fp,
            capture_output=True,
            text=False,
        )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    xml = result.stdout.decode("utf-8", "replace")

    # Run our extractor
    py_result = maps.extract(map_scen, tmp_path / "Maps")
    assert py_result["level_count"] == 37

    # Compare chunk sizes across all levels
    chunks_matched = chunks_total = polys_matched = 0
    for li in range(37):
        ei = xml.find(f'<entry index="{li}">')
        ee = xml.find(f'<entry index="{li+1}">') if li < 36 else len(xml)
        lev_xml = xml[ei:ee]
        perl_chunks = {m.group(1): int(m.group(2))
                       for m in re.finditer(r'<chunk type="(\S+?)" size="(\d+)"', lev_xml)}

        json_path = next((tmp_path / "Maps").glob(f"{li:02d}_*.json"))
        j = json.loads(json_path.read_text())
        py_chunks = {k: v for k, v in j["chunk_sizes"].items() if v > 0}

        for tag, sz in perl_chunks.items():
            chunks_total += 1
            if py_chunks.get(tag) == sz:
                chunks_matched += 1

        # Per-polygon floor/ceiling sanity
        for m in re.finditer(
            r'<polygon index="(\d+)"[^/]*?floor_height="(-?\d+)"[^/]*?ceiling_height="(-?\d+)"',
            lev_xml,
        ):
            idx, fh, ch = int(m.group(1)), int(m.group(2)), int(m.group(3))
            py_poly = j["data"]["POLY"][idx]
            assert py_poly["floor_height"] == fh
            assert py_poly["ceiling_height"] == ch
            polys_matched += 1

    assert chunks_matched == chunks_total, \
        f"chunk-size mismatch: {chunks_matched}/{chunks_total}"
    assert polys_matched > 7000  # all polys across all levels
