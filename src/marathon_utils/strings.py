"""Mac OS string resource extractor (`STR `, `STR#`, `TEXT`).

Port of `strings2xml.pl` from Hopper262/marathon-utils. Useful for pulling
Marathon's chapter titles, terminal lore, save-game prompts, weapon names,
and other UI text out of `Marathon.appl` (and its M2/Infinity equivalents,
which embed their own copies of the same resource types).

Marathon stores some of this directly in the application's resource fork:

- `STR ` (with trailing space) — a single Pascal-style MacRoman string
- `STR#`                       — an indexed list of Pascal-style strings
- `TEXT`                       — a long uint16-length-prefixed plain text blob

The Aleph One MML scripting system can override these via `<stringset>`
elements, and `rsrc2mml.pl` produces MML from them. This module returns the
strings as structured Python so you can re-emit MML, JSON, or whatever you
need.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

from . import macbinary, macrsrc


def _pstr(data: bytes, off: int) -> tuple[str, int]:
    """Read a classic Pascal-style string (1-byte length + MacRoman bytes).
    Returns (decoded_string, bytes_consumed)."""
    if off >= len(data):
        return "", 0
    n = data[off]
    end = off + 1 + n
    raw = data[off + 1: end]
    return raw.decode("mac-roman", errors="replace"), 1 + n


def parse_str(payload: bytes) -> str:
    """Decode a single `STR ` resource."""
    s, _ = _pstr(payload, 0)
    return s


def parse_strs(payload: bytes) -> list[str]:
    """Decode a `STR#` resource into an ordered list of strings."""
    if len(payload) < 2:
        return []
    n = struct.unpack(">H", payload[0:2])[0]
    out: list[str] = []
    pos = 2
    for _ in range(n):
        if pos >= len(payload):
            break
        s, used = _pstr(payload, pos)
        out.append(s)
        pos += used
    return out


def parse_text(payload: bytes) -> str:
    """Decode a `TEXT` resource (no length prefix — entire payload is text)."""
    return payload.decode("mac-roman", errors="replace")


# ---------------------------------------------------------------------------
# Interface resources used by rsrc2mml.pl: clut (colors), nrct (rectangles),
# finf (font info). These define HUD layout and terminal styling that Aleph
# One MML can override.
# ---------------------------------------------------------------------------

# Per the upstream M1 → M2 MML index remap table:
_M1_COLOR_LOOKUP = [*range(14), -1, 16, 17, 14, 15]
_M1_RECT_LOOKUP = (
    [-1, -1, -1, -1, -1,
     0, 1, 2, 3, 4,
     -1, 30, 5, 6,
     -1, -1, -1, -1, -1,
     21, 22, 20, 23, 24, 25, 26, 27, 28, 29,
     7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17,
     -1, -1, -1]
)


def parse_clut(payload: bytes, is_m1: bool = False) -> list[dict]:
    """Decode a Mac `clut` resource into a list of interface color overrides.

    Returns `[{"index": int, "red": float, "green": float, "blue": float}, ...]`
    where colors are 0.0..1.0. The 5000-style header is skipped; for M1 the
    indices are remapped to their M2/Infinity equivalents.
    """
    if len(payload) < 8:
        return []
    # 6 bytes header skip + uint16 count_minus_1
    count = struct.unpack(">H", payload[6:8])[0] + 1
    out: list[dict] = []
    pos = 8
    for i in range(count):
        if pos + 8 > len(payload):
            break
        # 2 bytes per-entry padding + 6 bytes RGB
        r, g, b = struct.unpack(">HHH", payload[pos + 2: pos + 8])
        pos += 8
        idx = _M1_COLOR_LOOKUP[i] if is_m1 and i < len(_M1_COLOR_LOOKUP) else i
        if idx < 0:
            continue
        out.append({
            "index": idx,
            "red": r / 65535,
            "green": g / 65535,
            "blue": b / 65535,
        })
    return out


def parse_nrct(payload: bytes, is_m1: bool = False) -> list[dict]:
    """Decode a Mac `nrct` resource (network/UI rectangles)."""
    if len(payload) < 2:
        return []
    count = struct.unpack(">H", payload[0:2])[0]
    out: list[dict] = []
    pos = 2
    for i in range(count):
        if pos + 8 > len(payload):
            break
        top, left, bottom, right = struct.unpack(">hhhh", payload[pos: pos + 8])
        pos += 8
        idx = _M1_RECT_LOOKUP[i] if is_m1 and i < len(_M1_RECT_LOOKUP) else i
        if idx < 0:
            continue
        out.append({"index": idx, "top": top, "left": left,
                    "bottom": bottom, "right": right})
    return out


def parse_finf(payload: bytes) -> list[dict]:
    """Decode a `finf` (font info) resource."""
    if len(payload) < 2:
        return []
    count = struct.unpack(">H", payload[0:2])[0]
    out: list[dict] = []
    pos = 2
    for i in range(count):
        if pos + 6 > len(payload):
            break
        file_id, style, size = struct.unpack(">HHH", payload[pos: pos + 6])
        pos += 6
        out.append({"index": i, "file": f"#{file_id}",
                    "style": style, "size": size})
    return out


def parse_m1_terminal_resource(payload: bytes) -> str:
    """Decode a Marathon 1 `term` resource as human-readable script text.

    M1 stores terminals as a scripting-language source format (lines starting
    with `;` are level/screen metadata, `#logon`/`#logoff`/`#information`/etc.
    are screen directives). M2/Infinity compile this into a binary chunk
    inside the level WAD — see `maps.parse_terminal` for that path.
    """
    text = payload.decode("mac-roman", errors="replace")
    # Normalize classic Mac line endings (\r) to \n for Python-friendliness
    return text.replace("\r\n", "\n").replace("\r", "\n")


def extract(source_path: Path | str, dest_dir: Path | str | None = None) -> dict:
    """Extract STR/STR#/TEXT resources from any MacBinary-wrapped Aleph One
    file (typically `Marathon.appl` or its M2/Infinity equivalent).

    If `dest_dir` is provided, also writes:
        <dest>/strings.json    -- structured dump
        <dest>/strings.txt     -- human-readable

    Returns a dict::

        {
          "STR":    {id: "single string", ...},
          "STR#":   {id: ["entry0", "entry1", ...], ...},
          "TEXT":   {id: "long text body", ...},
        }
    """
    blob = Path(source_path).read_bytes()
    _data, rsrc, _meta = macbinary.unwrap(blob)
    if rsrc is None:
        rsrc = blob

    resources = macrsrc.parse(rsrc)

    # Detect M1 vs M2: M1 has `clut` id 129 as a marker
    is_m1 = any(e["id"] == 129 for e in resources.get("clut", []))

    result: dict = {
        "STR": {}, "STR#": {}, "TEXT": {}, "term": {},
        "interface": {"color": [], "rect": [], "font": []},
        "is_m1": is_m1,
    }
    for entry in resources.get("STR ", []):
        result["STR"][entry["id"]] = parse_str(entry["data"])
    for entry in resources.get("STR#", []):
        result["STR#"][entry["id"]] = parse_strs(entry["data"])
    for entry in resources.get("TEXT", []):
        result["TEXT"][entry["id"]] = parse_text(entry["data"])
    for entry in resources.get("term", []):
        # M1 stores these as human-readable scripts; M2 compiles them into
        # WAD chunks. If the payload begins with ASCII `;` it's the M1 form.
        if entry["data"] and entry["data"][:1] in (b";", b"#"):
            result["term"][entry["id"]] = parse_m1_terminal_resource(entry["data"])

    # Interface overrides: clut 130 (M2) or clut 129 (M1 marker variant);
    # nrct 128; finf 128. These let Aleph One MML override HUD layout.
    for entry in resources.get("clut", []):
        if entry["id"] in (129, 130):
            result["interface"]["color"] = parse_clut(entry["data"], is_m1=is_m1)
            break
    for entry in resources.get("nrct", []):
        if entry["id"] == 128:
            result["interface"]["rect"] = parse_nrct(entry["data"], is_m1=is_m1)
            break
    for entry in resources.get("finf", []):
        if entry["id"] == 128:
            result["interface"]["font"] = parse_finf(entry["data"])
            break

    if dest_dir is not None:
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "strings.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        lines: list[str] = []
        for sid, s in sorted(result["STR"].items()):
            lines.append(f"--- STR  #{sid} ---\n{s}\n")
        for sid, entries in sorted(result["STR#"].items()):
            lines.append(f"--- STR# #{sid} ({len(entries)} entries) ---")
            for i, s in enumerate(entries):
                lines.append(f"  [{i:3d}] {s}")
            lines.append("")
        for sid, t in sorted(result["TEXT"].items()):
            lines.append(f"--- TEXT #{sid} ({len(t)} chars) ---\n{t}\n")
        if result["term"]:
            lines.append("")
            for sid, t in sorted(result["term"].items()):
                lines.append(f"=== term #{sid} ({len(t)} chars) ===")
                lines.append(t)
                lines.append("")
        (dest / "strings.txt").write_text("\n".join(lines), encoding="utf-8")
        # Terminals also get a per-id file each, easier for diffing
        if result["term"]:
            tdir = dest / "terminals"
            tdir.mkdir(exist_ok=True)
            for sid, t in result["term"].items():
                (tdir / f"term_{sid:04d}.txt").write_text(t, encoding="utf-8")

    return result


def to_mml(strings: dict, *, encoding_marker: bool = True) -> str:
    """Render an extract() result as Aleph One MML XML.

    Produces the same output as `rsrc2mml.pl`: an `<interface>` block with
    color/rect/font overrides plus one `<stringset>` per STR# resource.
    Useful for repackaging into scenario plugins or as override stringsets
    in scripted scenarios.
    """
    out: list[str] = []
    if encoding_marker:
        out.append('<?xml version="1.0"?>')
        out.append('<marathon>')

    iface = strings.get("interface", {})
    has_iface = any(iface.get(k) for k in ("color", "rect", "font"))
    if has_iface:
        out.append('  <interface>')
        for c in iface.get("color", []):
            out.append(f'    <color index="{c["index"]}" '
                        f'red="{c["red"]:.5f}" green="{c["green"]:.5f}" '
                        f'blue="{c["blue"]:.5f}"/>')
        for r in iface.get("rect", []):
            out.append(f'    <rect index="{r["index"]}" '
                        f'top="{r["top"]}" left="{r["left"]}" '
                        f'bottom="{r["bottom"]}" right="{r["right"]}"/>')
        for f in iface.get("font", []):
            out.append(f'    <font index="{f["index"]}" '
                        f'file="{f["file"]}" style="{f["style"]}" '
                        f'size="{f["size"]}"/>')
        out.append('  </interface>')

    for sid, entries in sorted(strings.get("STR#", {}).items()):
        out.append(f'  <stringset index="{sid}">')
        for i, s in enumerate(entries):
            safe = _xml_escape(s)
            out.append(f'    <string index="{i}">{safe}</string>')
        out.append('  </stringset>')
    if encoding_marker:
        out.append('</marathon>')
    return "\n".join(out)


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))
