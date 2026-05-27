"""Marathon 1 Map.scen extractor.

Reads the MacBinary-wrapped WAD container, walks per-level chunks, and emits
JSON describing geometry, lights, object placements, and terminal text. This
JSON is the input to the UE5 procedural-mesh converter.

Field byte layouts: see Tools/extract/FORMAT_NOTES.md (sourced from
marathon-utils/map2xml.pl and Aleph One headers).
"""
import json
import struct
from pathlib import Path
from typing import List

from . import macbinary, wad


def _u16(b: bytes, off: int) -> int:
    return struct.unpack(">H", b[off: off + 2])[0]


def _s16(b: bytes, off: int) -> int:
    return struct.unpack(">h", b[off: off + 2])[0]


def _u32(b: bytes, off: int) -> int:
    return struct.unpack(">I", b[off: off + 4])[0]


def _s32(b: bytes, off: int) -> int:
    return struct.unpack(">i", b[off: off + 4])[0]


# ---------------------------------------------------------------------------
# Chunk decoders
# Each returns a list of records (dicts) for one chunk's payload.
# ---------------------------------------------------------------------------

def parse_epnt(data: bytes) -> List[dict]:
    """Endpoints — 16 B records."""
    out = []
    for off in range(0, len(data) - 15, 16):
        out.append({
            "flags": _u16(data, off + 0),
            "highest_floor": _s16(data, off + 2),
            "lowest_ceiling": _s16(data, off + 4),
            "x": _s16(data, off + 6),
            "y": _s16(data, off + 8),
            "supporting_poly": _s16(data, off + 14),
        })
    return out


def parse_pnts(data: bytes) -> List[dict]:
    """Points — 4 B records (legacy form). Used when EPNT is absent."""
    out = []
    for off in range(0, len(data) - 3, 4):
        out.append({"x": _s16(data, off + 0), "y": _s16(data, off + 2)})
    return out


def parse_lins(data: bytes) -> List[dict]:
    """Lines — 32 B records."""
    out = []
    for off in range(0, len(data) - 31, 32):
        out.append({
            "endpoint1": _s16(data, off + 0),
            "endpoint2": _s16(data, off + 2),
            "flags": _u16(data, off + 4),
            "length": _s16(data, off + 6),
            "highest_floor": _s16(data, off + 8),
            "lowest_ceiling": _s16(data, off + 10),
            "cw_side": _s16(data, off + 12),
            "ccw_side": _s16(data, off + 14),
            "cw_poly": _s16(data, off + 16),
            "ccw_poly": _s16(data, off + 18),
        })
    return out


def parse_sids(data: bytes) -> List[dict]:
    """Sides / wall surfaces — 64 B records."""
    out = []
    for off in range(0, len(data) - 63, 64):
        out.append({
            "type": _s16(data, off + 0),
            "flags": _u16(data, off + 2),
            "primary":     {"x": _s16(data, off + 4),  "y": _s16(data, off + 6),  "shape": _u16(data, off + 8)},
            "secondary":   {"x": _s16(data, off + 10), "y": _s16(data, off + 12), "shape": _u16(data, off + 14)},
            "transparent": {"x": _s16(data, off + 16), "y": _s16(data, off + 18), "shape": _u16(data, off + 20)},
            "panel_type": _s16(data, off + 38),
            "panel_perm": _s16(data, off + 40),
            "poly_index": _s16(data, off + 48),
            "line_index": _s16(data, off + 50),
            "ambient_delta": _s32(data, off + 58),
        })
    return out


def parse_poly(data: bytes) -> List[dict]:
    """Polygons — 128 B records. We keep the geometry-relevant subset."""
    out = []
    rec_size = 128
    for off in range(0, len(data) - (rec_size - 1), rec_size):
        vertex_count = _u16(data, off + 6)
        endpoints = [_s16(data, off + 8 + i * 2) for i in range(8)][:vertex_count]
        line_indices = [_s16(data, off + 24 + i * 2) for i in range(8)][:vertex_count]
        side_indices = [_s16(data, off + 92 + i * 2) for i in range(8)][:vertex_count]
        adjacent = [_s16(data, off + 68 + i * 2) for i in range(8)][:vertex_count]
        out.append({
            "type": _s16(data, off + 0),
            "flags": _u16(data, off + 2),
            "permutation": _s16(data, off + 4),
            "vertex_count": vertex_count,
            "endpoints": endpoints,
            "lines": line_indices,
            "sides": side_indices,
            "adjacent_polys": adjacent,
            "floor_shape": _u16(data, off + 40),
            "ceiling_shape": _u16(data, off + 42),
            "floor_height": _s16(data, off + 44),
            "ceiling_height": _s16(data, off + 46),
            "floor_light": _s16(data, off + 48),
            "ceiling_light": _s16(data, off + 50),
            "first_object": _s16(data, off + 56),
            "center_x": _s16(data, off + 88),
            "center_y": _s16(data, off + 90),
            "media_index": _s16(data, off + 116),
            "ambient_sound": _s16(data, off + 122),
        })
    return out


def parse_lite(data: bytes) -> List[dict]:
    """Lights — M1 32 B records (very different from M2's 80+ B record!)."""
    out = []
    rec_size = 32
    for off in range(0, len(data) - (rec_size - 1), rec_size):
        out.append({
            "flags": _u16(data, off + 0),
            "type": _s16(data, off + 2),
            "mode": _s16(data, off + 4),
            "phase": _s16(data, off + 6),
            "min_intensity": _s32(data, off + 8) / 65536.0,
            "max_intensity": _s32(data, off + 12) / 65536.0,
            "period": _s16(data, off + 16),
            "intensity": _s32(data, off + 18) / 65536.0,
        })
    return out


def parse_objs(data: bytes) -> List[dict]:
    """Object placements — 16 B records."""
    out = []
    for off in range(0, len(data) - 15, 16):
        out.append({
            "type": _s16(data, off + 0),
            "object_index": _s16(data, off + 2),
            "facing": _s16(data, off + 4),
            "polygon_index": _s16(data, off + 6),
            "x": _s16(data, off + 8),
            "y": _s16(data, off + 10),
            "z": _s16(data, off + 12),
            "flags": _u16(data, off + 14),
        })
    return out


def parse_minf(data: bytes) -> dict:
    """Static map info — single 88 B record."""
    if len(data) < 88:
        return {}
    return {
        "environment_code": _s16(data, 0),
        "physics_model": _s16(data, 2),
        "song_index": _s16(data, 4),
        "mission_flags": _s16(data, 6),
        "environment_flags": _s16(data, 8),
        "level_name": data[18:18 + 66].split(b"\x00", 1)[0].decode("mac-roman", "replace"),
        "entry_point_flags": _u32(data, 84),
    }


def parse_name(data: bytes) -> str:
    return data.split(b"\x00", 1)[0].decode("mac-roman", "replace")


def parse_terminal(data: bytes) -> List[dict]:
    """Terminal data — each terminal: 10 B header, then groupings, font changes, text.
    Text may be XOR-obfuscated (flags bit 0). De-obfuscate per map2xml.pl.
    """
    out = []
    pos = 0
    while pos + 10 <= len(data):
        total_length = _u16(data, pos + 0)
        flags = _u16(data, pos + 2)
        lines_per_page = _s16(data, pos + 4)
        grouping_count = _u16(data, pos + 6)
        fontchange_count = _u16(data, pos + 8)
        body_start = pos + 10 + grouping_count * 12 + fontchange_count * 6
        body_end = pos + total_length
        if body_end > len(data) or body_start > body_end:
            break
        text_bytes = bytearray(data[body_start: body_end])
        if flags & 1:
            # De-obfuscate: XOR bytes 2 and 3 of every 4-byte block, plus tail
            n = len(text_bytes)
            full_blocks = (n // 4) * 4
            for i in range(0, full_blocks, 4):
                text_bytes[i + 2] ^= 0xFE
                text_bytes[i + 3] ^= 0xED
            for i in range(full_blocks, n):
                text_bytes[i] ^= 0xFE
        out.append({
            "flags": flags,
            "lines_per_page": lines_per_page,
            "grouping_count": grouping_count,
            "fontchange_count": fontchange_count,
            "text": bytes(text_bytes).decode("mac-roman", errors="replace"),
        })
        pos = body_end
        if total_length == 0:
            break
    return out


# Map of chunk tag → parser function
CHUNK_PARSERS = {
    b"EPNT": parse_epnt,
    b"PNTS": parse_pnts,
    b"LINS": parse_lins,
    b"SIDS": parse_sids,
    b"POLY": parse_poly,
    b"LITE": parse_lite,
    b"OBJS": parse_objs,
    b"Minf": parse_minf,
    b"NAME": parse_name,
    b"term": parse_terminal,
}


def parse_level(level_blob: bytes, level_entry: dict, hdr: dict) -> dict:
    """Parse a single level's chunks into a structured dict."""
    chunks_raw = {}
    parsed = {}
    for tag, data in wad.read_chunks(level_blob, level_entry, hdr["entry_header_size"]):
        tag_name = wad.tag_str(tag)
        chunks_raw[tag_name] = len(data)
        parser = CHUNK_PARSERS.get(tag)
        if parser is not None:
            try:
                parsed[tag_name] = parser(data)
            except Exception as e:
                parsed[tag_name] = {"_error": str(e), "_bytes": len(data)}
    return {
        "index": level_entry["index"],
        "wad_offset": level_entry["offset"],
        "wad_length": level_entry["length"],
        "chunk_sizes": chunks_raw,
        "data": parsed,
    }


def extract(source_path: Path, dest_dir: Path) -> dict:
    """Extract every level from Map.scen as JSON files in dest_dir."""
    blob = Path(source_path).read_bytes()
    data_fork, _rsrc, _meta = macbinary.unwrap(blob)
    if data_fork is None:
        data_fork = blob  # no MacBinary wrapper

    hdr = wad.read_header(data_fork)
    directory = wad.read_directory(data_fork, hdr)

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    levels_summary = []
    for entry in directory:
        if entry["length"] == 0:
            continue
        level = parse_level(data_fork, entry, hdr)
        # Pull level name from Minf or NAME chunk
        name = None
        if "Minf" in level["data"] and isinstance(level["data"]["Minf"], dict):
            name = level["data"]["Minf"].get("level_name")
        if not name and "NAME" in level["data"]:
            name = level["data"]["NAME"]
        if not name:
            name = f"Level_{entry['index']:02d}"
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()
        out_file = dest_dir / f"{entry['index']:02d}_{safe}.json"
        out_file.write_text(json.dumps(level, indent=2), encoding="utf-8")
        levels_summary.append({
            "index": entry["index"],
            "name": name,
            "path": out_file.name,
            "chunks": list(level["chunk_sizes"].keys()),
            "polygon_count": len(level["data"].get("POLY", []) or []),
            "endpoint_count": len(level["data"].get("EPNT", []) or []),
            "line_count": len(level["data"].get("LINS", []) or []),
        })
    return {
        "wad_header": {
            "version": hdr["version"],
            "name": hdr["name"],
            "wad_count": hdr["wad_count"],
        },
        "level_count": len(levels_summary),
        "levels": levels_summary,
    }
