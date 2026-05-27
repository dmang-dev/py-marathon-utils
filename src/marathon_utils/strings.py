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

    result: dict = {"STR": {}, "STR#": {}, "TEXT": {}, "term": {}}
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
    """Render an extract() result as Aleph One MML <stringset> blocks.

    This is the format `rsrc2mml.pl` produces; useful for repackaging into
    scenario plugins or as override stringsets in scripted scenarios.
    """
    out: list[str] = []
    if encoding_marker:
        out.append('<?xml version="1.0"?>')
        out.append('<marathon>')
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
