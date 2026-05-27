"""Anvil-format shape patch reader and applier.

Anvil patches are how Aleph One community plugins distribute texture/sprite
overrides — e.g. HD texture packs for Marathon 1/2/Infinity. Each patch is a
sequence of per-collection blocks containing only the records that need to
change (sparse override).

This is a Python port of `patch2xml.pl` plus an actual `apply()` that does
what upstream's `applypatch.pl` only stubbed out (`# tbd`).

Binary layout (all big-endian):

    Per collection block:
        uint32 collection_index
        uint32 bit_depth        (typically 8 or 16)
        Sequence of chunks until "endc":
            char[4] tag         ("cldf", "ctab", "hlsh", "llsh", "bmap", "endc")
            [tag-specific payload]

Chunks:
    cldf — full collection definition (560 B, same as shapes header)
    ctab — int32 index + (color_count * 8 B) color entries
    hlsh — int32 index + int32 size + high-level shape header + frame indices
    llsh — int32 index + 36 B low-level shape transform
    bmap — int32 index + int32 size + bitmap header + payload
    endc — end-of-collection marker

Output: structured Python dict listing the overrides, plus an `apply()` that
overlays them onto a `marathon_utils.shapes.parse_collection` result.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path


def _shapes_module():
    """Lazy import of `shapes` so the package loads without Pillow."""
    from . import shapes as _shapes
    return _shapes


def _u32(b: bytes, off: int) -> int:
    return struct.unpack(">I", b[off: off + 4])[0]


def _s32(b: bytes, off: int) -> int:
    return struct.unpack(">i", b[off: off + 4])[0]


def _u16(b: bytes, off: int) -> int:
    return struct.unpack(">H", b[off: off + 2])[0]


def _s16(b: bytes, off: int) -> int:
    return struct.unpack(">h", b[off: off + 2])[0]


def _u8(b: bytes, off: int) -> int:
    return b[off]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse(blob: bytes) -> dict:
    """Parse an Anvil patch file. Returns::

        {
          "collections": [
            {
              "index": <int>,
              "bit_depth": 8 | 16,
              "definition": {<560-B coll header>} | None,
              "color_tables": [{index: <int>, colors: [...]}, ...],
              "high_shapes":  [{index: <int>, ...}, ...],
              "low_shapes":   [{index: <int>, ...}, ...],
              "bitmaps":      [{index: <int>, bitmap: <Bitmap>}, ...],
            }, ...
          ]
        }
    """
    _shapes = _shapes_module()  # lazy import (needs Pillow)
    pos = 0
    collections: list[dict] = []

    while pos + 8 <= len(blob):
        coll_idx = _s32(blob, pos)
        bit_depth = _s32(blob, pos + 4)
        pos += 8

        coll: dict = {
            "index": coll_idx,
            "bit_depth": bit_depth,
            "definition": None,
            "color_tables": [],
            "high_shapes": [],
            "low_shapes": [],
            "bitmaps": [],
        }
        color_count = 0

        while pos + 4 <= len(blob):
            tag = blob[pos: pos + 4]
            pos += 4

            if tag == b"endc":
                break

            if tag == b"cldf":
                hdr_bytes = blob[pos: pos + 560]
                pos += 560
                hdr = _shapes.parse_collection_header(hdr_bytes)
                coll["definition"] = hdr
                color_count = hdr["color_count"]

            elif tag == b"ctab":
                idx = _s32(blob, pos)
                pos += 4
                # Each color is 8 bytes; we trust the cldf-supplied color_count.
                if color_count <= 0:
                    color_count = (len(blob) - pos) // 8  # best-effort fallback
                colors = []
                for _i in range(color_count):
                    flags = _u8(blob, pos + 0)
                    val = _u8(blob, pos + 1)
                    r = _u16(blob, pos + 2) >> 8
                    g = _u16(blob, pos + 4) >> 8
                    b = _u16(blob, pos + 6) >> 8
                    pos += 8
                    colors.append({
                        "self_luminescent": bool(flags & 0x80),
                        "value": val, "r": r, "g": g, "b": b,
                    })
                coll["color_tables"].append({"index": idx, "colors": colors})

            elif tag == b"hlsh":
                idx = _s32(blob, pos)
                pos += 4
                _size = _s32(blob, pos)
                pos += 4
                # Parse the high-level shape header (88 B) starting at pos
                hs = _shapes.parse_high_shape(blob, pos)
                pos += 88
                # Frame indices: low_shape_indices already determined by hs[
                # 'effective_views' * 'frames_per_view']
                framect = max(0, hs["effective_views"]) * max(0, hs["frames_per_view"])
                frames = [_s16(blob, pos + i * 2) for i in range(framect)]
                pos += framect * 2
                # Terminator int16
                pos += 2
                coll["high_shapes"].append({"index": idx, "shape": hs,
                                            "frame_indices": frames})

            elif tag == b"llsh":
                idx = _s32(blob, pos)
                pos += 4
                ls = _shapes.parse_low_shape(blob, pos)
                pos += 36
                coll["low_shapes"].append({"index": idx, "low_shape": ls})

            elif tag == b"bmap":
                idx = _s32(blob, pos)
                pos += 4
                _size = _s32(blob, pos)
                pos += 4
                # Bitmap header + payload. The shapes module already knows how
                # to decode both M1 and M2 layouts — we determine which by the
                # collection's bit_depth and the bitmap flags.
                # parse_bitmap expects an offset within `data`; we pass the
                # rest of the blob from `pos` and feed pos as 0.
                rest = blob[pos:]
                # Try M2 sparse first when bytes_per_row == -1
                bytes_per_row = _s16(rest, 4)
                fmt_version = 2 if bytes_per_row < 0 else 1
                bm = _shapes.parse_bitmap(rest, 0, format_version=fmt_version)
                # Compute consumed bytes by walking the same layout
                consumed = _bitmap_size_in_blob(rest, bm, fmt_version)
                pos += consumed
                coll["bitmaps"].append({"index": idx, "bitmap": bm})

            else:
                # Unknown chunk — bail to avoid drifting indices
                raise ValueError(f"unknown patch chunk tag {tag!r} at byte {pos-4}")

        collections.append(coll)

    return {"collections": collections}


def _bitmap_size_in_blob(rest: bytes, bm, fmt_version: int) -> int:
    """Compute how many bytes a bitmap chunk consumed in the patch stream."""
    width = _s16(rest, 0)
    height = _s16(rest, 2)
    bytes_per_row = _s16(rest, 4)
    flags = _u16(rest, 6)
    column_order = bool(flags & 0x8000)
    table_count = (width if column_order else height) + 1
    base = 26 + 4 * table_count

    if bytes_per_row >= 0:
        line_count = width if column_order else height
        line_length = height if column_order else width
        return base + line_count * line_length

    if fmt_version >= 2:
        # M2 sparse: walk each column, accumulating size
        pos = base
        for _x in range(width):
            first_row = _s16(rest, pos)
            last_row = _s16(rest, pos + 2)
            pos += 4 + max(0, last_row - first_row)
        return pos

    # M1 RLE: walk row/column opcodes
    line_count = width if column_order else height
    pos = base
    for _li in range(line_count):
        while True:
            op = _s16(rest, pos)
            pos += 2
            if op == 0:
                break
            if op > 0:
                pos += op
    return pos


# ---------------------------------------------------------------------------
# Top-level extractor
# ---------------------------------------------------------------------------

def extract(source_path: Path | str, dest_dir: Path | str) -> dict:
    """Read an Anvil patch file and write a manifest JSON.

    Note: Anvil patches are MacBinary-wrapped when distributed from older
    Marathon archives; we transparently unwrap.
    """
    blob = Path(source_path).read_bytes()
    from . import macbinary
    _data, rsrc, _meta = macbinary.unwrap(blob)
    payload = rsrc if rsrc else (blob if _data is None else _data)

    result = parse(payload)

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Strip Pillow bitmaps from the JSON manifest (they're not JSON-serializable
    # and the user can re-extract images via `apply()`).
    manifest = {"collections": []}
    for coll in result["collections"]:
        manifest["collections"].append({
            "index": coll["index"],
            "bit_depth": coll["bit_depth"],
            "has_definition": coll["definition"] is not None,
            "color_table_count": len(coll["color_tables"]),
            "high_shape_count": len(coll["high_shapes"]),
            "low_shape_count": len(coll["low_shapes"]),
            "bitmap_count": len(coll["bitmaps"]),
            "bitmap_indices": [b["index"] for b in coll["bitmaps"]],
        })
    (dest_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


# ---------------------------------------------------------------------------
# Apply a patch onto a parsed shapes result
# ---------------------------------------------------------------------------

def apply(parsed_collections: list[dict] | dict, patch: dict) -> dict:
    """Overlay a patch onto a dict of {collection_index: parsed_collection}.

    Accepts either:
      - a list of collection dicts (as returned by `shapes.extract()`'s
        per-collection iteration), keyed by their `index` somehow, or
      - a dict mapping collection_index -> parsed collection dict (the inner
        return value of `shapes.parse_collection`).

    Returns a dict mapping collection_index -> patched collection dict. The
    input is NOT mutated (we shallow-copy the affected collections first).
    """
    if isinstance(parsed_collections, list):
        base = {c.get("index", i): c for i, c in enumerate(parsed_collections)}
    else:
        base = dict(parsed_collections)

    summary = {"collections_touched": [], "details": []}
    for pcoll in patch["collections"]:
        idx = pcoll["index"]
        target = base.get(idx)
        if target is None:
            summary["details"].append({"collection": idx, "skipped": "not in base"})
            continue
        # Shallow copy so we don't mutate caller's data
        target = {**target}
        base[idx] = target

        if pcoll["definition"] is not None:
            target["header"] = pcoll["definition"]

        # Replace bitmaps in place by index
        if pcoll["bitmaps"]:
            bitmaps = list(target.get("bitmaps") or [])
            for entry in pcoll["bitmaps"]:
                while len(bitmaps) <= entry["index"]:
                    bitmaps.append(None)
                bitmaps[entry["index"]] = entry["bitmap"]
            target["bitmaps"] = bitmaps

        # Replace color tables
        if pcoll["color_tables"]:
            cluts = list(target.get("cluts") or [])
            for entry in pcoll["color_tables"]:
                while len(cluts) <= entry["index"]:
                    cluts.append([(0, 0, 0)] * 256)
                # Convert structured colors back to (r,g,b) tuples
                palette: list[tuple[int, int, int]] = [(0, 0, 0)] * 256
                for c in entry["colors"]:
                    if 0 <= c["value"] < 256:
                        palette[c["value"]] = (c["r"], c["g"], c["b"])
                cluts[entry["index"]] = palette
            target["cluts"] = cluts

        # Replace high/low shapes
        if pcoll["high_shapes"]:
            high = list(target.get("high_shapes") or [])
            for entry in pcoll["high_shapes"]:
                while len(high) <= entry["index"]:
                    high.append(None)
                merged = dict(entry["shape"])
                merged["low_shape_indices"] = entry["frame_indices"]
                high[entry["index"]] = merged
            target["high_shapes"] = high
        if pcoll["low_shapes"]:
            low = list(target.get("low_shapes") or [])
            for entry in pcoll["low_shapes"]:
                while len(low) <= entry["index"]:
                    low.append(None)
                low[entry["index"]] = entry["low_shape"]
            target["low_shapes"] = low

        summary["collections_touched"].append(idx)
        summary["details"].append({
            "collection": idx,
            "bitmaps_replaced": [b["index"] for b in pcoll["bitmaps"]],
            "color_tables_replaced": [c["index"] for c in pcoll["color_tables"]],
            "high_shapes_replaced": [h["index"] for h in pcoll["high_shapes"]],
            "low_shapes_replaced": [entry["index"] for entry in pcoll["low_shapes"]],
        })

    return {"collections": base, "summary": summary}
