"""Marathon 1 Shapes.shps extractor.

Ports `m1shapes2xml.pl` + `shapesxml2images.pl` from Hopper262/marathon-utils
into a single binary-to-PNG pipeline. Reads MacBinary-wrapped Shapes.shps,
decodes per-collection CLUTs and bitmaps (including M1's row/column RLE),
and writes PNG files plus a JSON manifest.

Output layout::

    <dest>/manifest.json
    <dest>/Coll_<NN>/palette.png            # 16x16 swatch of the default CLUT
    <dest>/Coll_<NN>/bitmaps/<NNN>.png      # one per bitmap, decoded
    <dest>/Coll_<NN>/shapes.json            # high-level shape sequences
    <dest>/Coll_<NN>/sprites/<NNN>.png      # composited high-level shape frames

Requires Pillow (`pip install Pillow`).
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

from PIL import Image

from . import macbinary, macrsrc

# ---------------------------------------------------------------------------
# Low-level byte readers
# ---------------------------------------------------------------------------

def _u16(b: bytes, off: int) -> int:
    return struct.unpack(">H", b[off: off + 2])[0]


def _s16(b: bytes, off: int) -> int:
    return struct.unpack(">h", b[off: off + 2])[0]


def _u32(b: bytes, off: int) -> int:
    return struct.unpack(">I", b[off: off + 4])[0]


def _s32(b: bytes, off: int) -> int:
    return struct.unpack(">i", b[off: off + 4])[0]


# ---------------------------------------------------------------------------
# Collection header (560 bytes)
# ---------------------------------------------------------------------------

def parse_collection_header(data: bytes) -> dict:
    return {
        "version": _s16(data, 0),
        "type": _s16(data, 2),
        "flags": _u16(data, 4),
        "color_count": _s16(data, 6),
        "clut_count": _s16(data, 8),
        "color_table_offset": _s32(data, 10),
        "high_shape_count": _s16(data, 14),
        "high_shape_table_offset": _s32(data, 16),
        "low_shape_count": _s16(data, 20),
        "low_shape_table_offset": _s32(data, 22),
        "bitmap_count": _s16(data, 26),
        "bitmap_table_offset": _s32(data, 28),
        "pixels_to_world": _s16(data, 32),
        "collection_size": _s32(data, 34),
    }


# ---------------------------------------------------------------------------
# Color tables (CLUTs)
# ---------------------------------------------------------------------------

def parse_clut(data: bytes, base: int, color_count: int) -> list[tuple[int, int, int]]:
    """Read one color table starting at base. Returns 256 RGB triples (8-bit),
    indexed by palette slot. Sparse CLUTs are honored via the per-entry `value`.
    """
    palette: list[tuple[int, int, int]] = [(0, 0, 0)] * 256
    for i in range(color_count):
        off = base + i * 8
        flags = data[off]  # noqa: F841 — flags reserved for future use
        slot = data[off + 1]
        r = _u16(data, off + 2) >> 8
        g = _u16(data, off + 4) >> 8
        b = _u16(data, off + 6) >> 8
        if 0 <= slot < 256:
            palette[slot] = (r, g, b)
    return palette


def parse_clut_set(data: bytes, hdr: dict) -> list[list[tuple[int, int, int]]]:
    """Return one palette list per CLUT in the collection."""
    out = []
    for ci in range(hdr["clut_count"]):
        base = hdr["color_table_offset"] + ci * hdr["color_count"] * 8
        out.append(parse_clut(data, base, hdr["color_count"]))
    return out


# ---------------------------------------------------------------------------
# Bitmaps
# ---------------------------------------------------------------------------

class Bitmap:
    """Decoded indexed-color bitmap. `indices` is a flat width*height byte array."""

    __slots__ = ("column_order", "flags", "height", "indices", "transparent", "width")

    def __init__(self, width: int, height: int, flags: int, indices: bytes):
        self.width = width
        self.height = height
        self.flags = flags
        self.column_order = bool(flags & 0x8000)
        self.transparent = bool(flags & 0x4000)
        self.indices = indices

    def to_image(self, palette: list[tuple[int, int, int]]) -> Image.Image:
        """Render to an RGBA Pillow image using the supplied palette."""
        img = Image.new("RGBA", (self.width, self.height))
        px = img.load()
        for y in range(self.height):
            for x in range(self.width):
                if self.column_order:
                    ci = self.indices[x * self.height + y]
                else:
                    ci = self.indices[y * self.width + x]
                r, g, b = palette[ci]
                a = 0 if (self.transparent and ci == 0) else 255
                px[x, y] = (r, g, b, a)
        return img


def parse_bitmap(data: bytes, base: int, format_version: int = 1) -> Bitmap:
    """Parse one bitmap (header + payload).

    `format_version`: 1 = M1 (row/column int16-opcode RLE when bytes_per_row<0),
                      2 = M2/Infinity (column-major sparse first_row/last_row).
    """
    width = _s16(data, base + 0)
    height = _s16(data, base + 2)
    bytes_per_row = _s16(data, base + 4)
    flags = _u16(data, base + 6)
    # bit_depth at base+8 is always 8 here; reserved bytes 10..25
    column_order = bool(flags & 0x8000)

    address_table_count = (width if column_order else height) + 1
    data_start = base + 26 + 4 * address_table_count

    if bytes_per_row >= 0:
        # Raw uncompressed: width*height bytes (row-major) regardless of column flag
        # (the address table is informational; we read sequentially).
        line_count = width if column_order else height
        line_length = height if column_order else width
        indices = bytearray(data[data_start: data_start + line_count * line_length])
        return Bitmap(width, height, flags, bytes(indices))

    # Compressed path differs by format
    if format_version >= 2:
        # M2 / Infinity: column-major sparse. For each column: int16 first_row,
        # int16 last_row, then (last_row - first_row) pixel bytes.
        indices = bytearray(width * height)  # row-major plane
        pos = data_start
        for x in range(width):
            if pos + 4 > len(data):
                break
            first_row = struct.unpack(">h", data[pos: pos + 2])[0]
            last_row = struct.unpack(">h", data[pos + 2: pos + 4])[0]
            pos += 4
            run = max(0, last_row - first_row)
            for y in range(run):
                if first_row + y < height and pos + y < len(data):
                    indices[(first_row + y) * width + x] = data[pos + y]
            pos += run
        # M2 always materializes as row-major; clear the column_order flag so
        # Bitmap.to_image() doesn't try to swap axes on read.
        flags_for_image = flags & ~0x8000
        return Bitmap(width, height, flags_for_image, bytes(indices))

    # M1 row/column int16-opcode RLE
    line_count = width if column_order else height
    line_length = height if column_order else width
    indices = bytearray(width * height)
    pos = data_start
    for li in range(line_count):
        line = bytearray(line_length)
        li_pos = 0
        while True:
            if pos + 2 > len(data):
                break
            op = struct.unpack(">h", data[pos: pos + 2])[0]
            pos += 2
            if op == 0:
                break
            if op > 0:
                line[li_pos: li_pos + op] = data[pos: pos + op]
                pos += op
                li_pos += op
            else:
                li_pos += -op  # zero-fill (already zero)
        # Write line back into the master grid
        if column_order:
            for y in range(line_length):
                indices[li * line_length + y] = line[y]
        else:
            indices[li * line_length: li * line_length + line_length] = line

    return Bitmap(width, height, flags, bytes(indices))


# ---------------------------------------------------------------------------
# High-level shapes (sprite sequences) — for the manifest only.
# ---------------------------------------------------------------------------

_EFFECTIVE_VIEWS = {10: 1, 3: 4, 9: 5, 11: 5, 5: 8}


def parse_high_shape(data: bytes, base: int) -> dict:
    name_len = data[base + 4]
    name = data[base + 5: base + 5 + name_len].decode("mac-roman", errors="replace")
    number_of_views = _s16(data, base + 38)
    frames_per_view = _s16(data, base + 40)
    effective_views = _EFFECTIVE_VIEWS.get(number_of_views, number_of_views)
    nframes = max(effective_views, 0) * max(frames_per_view, 0)
    low_indices = [_s16(data, base + 88 + i * 2) for i in range(nframes)] if nframes > 0 else []
    return {
        "type": _s16(data, base + 0),
        "flags": _u16(data, base + 2),
        "name": name,
        "number_of_views": number_of_views,
        "effective_views": effective_views,
        "frames_per_view": frames_per_view,
        "ticks_per_frame": _s16(data, base + 42),
        "key_frame": _s16(data, base + 44),
        "transfer_mode": _s16(data, base + 46),
        "transfer_mode_period": _s16(data, base + 48),
        "first_frame_sound": _s16(data, base + 50),
        "key_frame_sound": _s16(data, base + 52),
        "last_frame_sound": _s16(data, base + 54),
        "pixels_to_world": _s16(data, base + 56),
        "loop_frame": _s16(data, base + 58),
        "low_shape_indices": low_indices,
    }


def parse_low_shape(data: bytes, base: int) -> dict:
    return {
        "flags": _u16(data, base + 0),
        "min_light_intensity": _s32(data, base + 2) / 65536.0,
        "bitmap_index": _s16(data, base + 6),
        "origin_x": _s16(data, base + 8),
        "origin_y": _s16(data, base + 10),
        "key_x": _s16(data, base + 12),
        "key_y": _s16(data, base + 14),
        "world_left": _s16(data, base + 16),
        "world_right": _s16(data, base + 18),
        "world_top": _s16(data, base + 20),
        "world_bottom": _s16(data, base + 22),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _palette_swatch(palette: list[tuple[int, int, int]]) -> Image.Image:
    """16x16 swatch showing the entire palette (each cell is 8px)."""
    cell = 8
    img = Image.new("RGB", (16 * cell, 16 * cell), (0, 0, 0))
    px = img.load()
    for i in range(256):
        r, g, b = palette[i]
        cx = (i % 16) * cell
        cy = (i // 16) * cell
        for dy in range(cell):
            for dx in range(cell):
                px[cx + dx, cy + dy] = (r, g, b)
    return img


# ---------------------------------------------------------------------------
# Top-level extractor
# ---------------------------------------------------------------------------

def parse_collection(payload: bytes, format_version: int = 1) -> dict:
    """Parse the inner payload of one collection into a structured dict.

    For M1 (`format_version=1`) the caller passes the resource fork's already-
    unwrapped collection bytes. For M2/Infinity (`format_version=2`) the caller
    passes the slice from `off..off+len` of the outer file.
    """
    hdr = parse_collection_header(payload)
    cluts = parse_clut_set(payload, hdr)

    # Bitmap offset table: array of int32 offsets relative to collection start
    bitmap_offsets = [_s32(payload, hdr["bitmap_table_offset"] + i * 4)
                      for i in range(hdr["bitmap_count"])]
    high_offsets = [_s32(payload, hdr["high_shape_table_offset"] + i * 4)
                    for i in range(hdr["high_shape_count"])]
    low_offsets = [_s32(payload, hdr["low_shape_table_offset"] + i * 4)
                   for i in range(hdr["low_shape_count"])]

    bitmaps = [parse_bitmap(payload, off, format_version) for off in bitmap_offsets]
    high_shapes = [parse_high_shape(payload, off) for off in high_offsets]
    low_shapes = [parse_low_shape(payload, off) for off in low_offsets]

    return {
        "header": hdr,
        "cluts": cluts,
        "bitmaps": bitmaps,
        "high_shapes": high_shapes,
        "low_shapes": low_shapes,
    }


def _read_m2_table(blob: bytes) -> list[dict]:
    """Read the 32-entry collection-info table at the start of an M2 shapes file.

    Each entry (32 bytes): status, flags, off8, len8, off16, len16, 12 B padding.
    """
    table = []
    for i in range(32):
        off = i * 32
        if off + 32 > len(blob):
            break
        table.append({
            "status": _s16(blob, off + 0),
            "flags":  _u16(blob, off + 2),
            "off8":   _s32(blob, off + 4),
            "len8":   _s32(blob, off + 8),
            "off16":  _s32(blob, off + 12),
            "len16":  _s32(blob, off + 16),
        })
    return table


def _detect_format(blob: bytes) -> tuple[int, list]:
    """Return (format_version, collections_descriptor_list).

    For M1 the second element is the parsed rsrc fork's `.256` list. For M2 it
    is the 32-entry collection-info table.
    """
    _data, rsrc, _meta = macbinary.unwrap(blob)
    if rsrc:
        resources = macrsrc.parse(rsrc)
        coll_resources = resources.get(".256", [])
        if coll_resources:
            return 1, coll_resources
    # Not MacBinary or no .256 resources — assume M2/Infinity layout
    return 2, _read_m2_table(blob)


def extract(source_path: Path | str, dest_dir: Path | str,
            clut_index: int = 0) -> dict:
    """Extract a Shapes file to PNG files under dest_dir.

    Auto-detects M1 vs M2/Infinity. Each collection becomes its own
    subdirectory `Coll_<NN>`; the chosen CLUT becomes the palette for the
    bitmap PNGs.
    """
    blob = Path(source_path).read_bytes()
    format_version, collections = _detect_format(blob)

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict = {"format_version": format_version,
                      "collections": [], "errors": []}

    if format_version == 1:
        return _extract_m1(collections, dest_dir, clut_index, manifest)
    return _extract_m2(blob, collections, dest_dir, clut_index, manifest)


def _extract_m1(coll_resources, dest_dir, clut_index, manifest) -> dict:
    for res in coll_resources:
        coll_idx = res["id"] - 128  # M1 collection 0 = resource id 128
        coll_dir = dest_dir / f"Coll_{coll_idx:02d}"
        coll_dir.mkdir(parents=True, exist_ok=True)
        try:
            # macrsrc.parse() already stripped the 4-byte size prefix, so the
            # payload begins at the collection header.
            parsed = parse_collection(res["data"])
        except Exception as e:
            manifest["errors"].append({"collection": coll_idx, "error": str(e)})
            continue

        cluts = parsed["cluts"]
        active_clut = cluts[min(clut_index, len(cluts) - 1)] if cluts else [(0, 0, 0)] * 256

        # Palette swatch
        _palette_swatch(active_clut).save(coll_dir / "palette.png")

        # Bitmaps
        bitmaps_dir = coll_dir / "bitmaps"
        bitmaps_dir.mkdir(exist_ok=True)
        for bi, bm in enumerate(parsed["bitmaps"]):
            try:
                bm.to_image(active_clut).save(bitmaps_dir / f"{bi:03d}.png")
            except Exception as e:
                manifest["errors"].append({
                    "collection": coll_idx, "bitmap": bi, "error": str(e),
                })

        # High-level shape metadata
        shapes_meta = {
            "header": {k: v for k, v in parsed["header"].items()},
            "high_shapes": parsed["high_shapes"],
            "low_shapes": parsed["low_shapes"],
            "clut_count": len(cluts),
        }
        (coll_dir / "shapes.json").write_text(json.dumps(shapes_meta, indent=2),
                                              encoding="utf-8")

        manifest["collections"].append({
            "index": coll_idx,
            "resource_id": res["id"],
            "name": res["name"],
            "bitmap_count": len(parsed["bitmaps"]),
            "high_shape_count": len(parsed["high_shapes"]),
            "low_shape_count": len(parsed["low_shapes"]),
            "clut_count": len(cluts),
        })

    (dest_dir / "manifest.json").write_text(json.dumps(manifest, indent=2),
                                            encoding="utf-8")
    return manifest


def _extract_m2(blob: bytes, table: list, dest_dir: Path,
                clut_index: int, manifest: dict) -> dict:
    """Extract an M2 / Infinity shapes file. The 32-entry table at the start
    points to per-collection 8-bit and 16-bit data blocks; we render the 8-bit
    bank since that's what carries the palette-indexed sprites we need.
    """
    for coll_idx, entry in enumerate(table):
        off, length = entry["off8"], entry["len8"]
        if off <= 0 or length <= 0:
            continue
        if off + length > len(blob):
            manifest["errors"].append({"collection": coll_idx,
                                       "error": f"out-of-bounds slice {off}:{off + length}"})
            continue
        payload = blob[off:off + length]

        coll_dir = dest_dir / f"Coll_{coll_idx:02d}"
        coll_dir.mkdir(parents=True, exist_ok=True)
        try:
            parsed = parse_collection(payload, format_version=2)
        except Exception as e:
            manifest["errors"].append({"collection": coll_idx, "error": str(e)})
            continue

        cluts = parsed["cluts"]
        active_clut = cluts[min(clut_index, len(cluts) - 1)] if cluts else [(0, 0, 0)] * 256

        _palette_swatch(active_clut).save(coll_dir / "palette.png")

        bitmaps_dir = coll_dir / "bitmaps"
        bitmaps_dir.mkdir(exist_ok=True)
        for bi, bm in enumerate(parsed["bitmaps"]):
            try:
                bm.to_image(active_clut).save(bitmaps_dir / f"{bi:03d}.png")
            except Exception as e:
                manifest["errors"].append({
                    "collection": coll_idx, "bitmap": bi, "error": str(e),
                })

        shapes_meta = {
            "header": dict(parsed["header"]),
            "high_shapes": parsed["high_shapes"],
            "low_shapes": parsed["low_shapes"],
            "clut_count": len(cluts),
        }
        (coll_dir / "shapes.json").write_text(json.dumps(shapes_meta, indent=2),
                                              encoding="utf-8")

        manifest["collections"].append({
            "index": coll_idx,
            "status": entry["status"],
            "flags": entry["flags"],
            "bitmap_count": len(parsed["bitmaps"]),
            "high_shape_count": len(parsed["high_shapes"]),
            "low_shape_count": len(parsed["low_shapes"]),
            "clut_count": len(cluts),
        })

    (dest_dir / "manifest.json").write_text(json.dumps(manifest, indent=2),
                                            encoding="utf-8")
    return manifest


# ---------------------------------------------------------------------------
# Parsing into in-memory dicts (no PNG output) — input for the writer below
# ---------------------------------------------------------------------------

def parse_m2_collections(blob: bytes) -> list[dict]:
    """Parse an M2 / Infinity Shapes file into per-collection dicts without
    rendering. Companion to `write_m2()` for round-tripping.

    Returns a list of `{index, status, flags, bit_depth, header, cluts,
    bitmaps, high_shapes, low_shapes}` dicts. Empty slots in the outer
    32-entry collection table are omitted.
    """
    table = _read_m2_table(blob)
    out: list[dict] = []
    for idx, entry in enumerate(table):
        off, length = entry["off8"], entry["len8"]
        if off <= 0 or length <= 0:
            continue
        payload = blob[off: off + length]
        try:
            parsed = parse_collection(payload, format_version=2)
        except Exception:
            continue
        out.append({
            "index": idx,
            "status": entry["status"],
            "flags": entry["flags"],
            "bit_depth": 8,
            **parsed,
        })
    return out


# ---------------------------------------------------------------------------
# Writer: shapes_collections -> binary M2 .shpA blob (port of xml2shapes.pl)
# ---------------------------------------------------------------------------

def _encode_bitmap_payload_raw(bm: Bitmap) -> bytes:
    width = bm.width
    height = bm.height
    flags = bm.flags & ~0x8000
    bytes_per_row = width
    header = struct.pack(">hhhHh", width, height, bytes_per_row, flags, 8)
    header += b"\x00" * 16
    addr_table = b"\x00" * (4 * (height + 1))
    if bm.column_order:
        pixels = bytes(bm.indices[x * height + y]
                       for y in range(height) for x in range(width))
    else:
        pixels = bytes(bm.indices)
    payload = header + addr_table + pixels
    pad = (-len(payload)) % 4
    return payload + b"\x00" * pad


def _encode_high_shape_record(shape: dict, frames: list[int]) -> bytes:
    name = shape.get("name", "").encode("mac-roman", errors="replace")[:33]
    header = struct.pack(
        ">hHB33s hhhh hh hhh hh",
        shape.get("type", 0),
        shape.get("flags", 0),
        len(name),
        name.ljust(33, b"\x00"),
        shape.get("number_of_views", 1),
        shape.get("frames_per_view", 0),
        shape.get("ticks_per_frame", 0),
        shape.get("key_frame", 0),
        shape.get("transfer_mode", 0),
        shape.get("transfer_mode_period", 0),
        shape.get("first_frame_sound", -1),
        shape.get("key_frame_sound", -1),
        shape.get("last_frame_sound", -1),
        shape.get("pixels_to_world", 1),
        shape.get("loop_frame", 0),
    ) + b"\x00" * 28
    frames_bytes = b"".join(struct.pack(">h", fi) for fi in frames)
    # 2-byte terminator after frames (per HandleHlsh in xml2shapes.pl)
    return header + frames_bytes + b"\x00\x00"


def _encode_low_shape_record(ls: dict) -> bytes:
    return struct.pack(
        ">Hi hhhhh hhhh hh",
        ls.get("flags", 0),
        int(ls.get("min_light_intensity", 0.0) * 65536),
        ls.get("bitmap_index", 0),
        ls.get("origin_x", 0),
        ls.get("origin_y", 0),
        ls.get("key_x", 0),
        ls.get("key_y", 0),
        ls.get("world_left", 0),
        ls.get("world_right", 0),
        ls.get("world_top", 0),
        ls.get("world_bottom", 0),
        ls.get("world_x0", 0),
        ls.get("world_y0", 0),
    ) + b"\x00" * 8


def _encode_clut(palette: list[tuple[int, int, int]], color_count: int) -> bytes:
    out = bytearray()
    for slot in range(color_count):
        r, g, b = palette[slot] if slot < len(palette) else (0, 0, 0)
        out += struct.pack(">BBHHH", 0, slot,
                            (r << 8) | r, (g << 8) | g, (b << 8) | b)
    return bytes(out)


def _encode_cldf_header(hdr: dict, ctab_off: int, color_count: int, clut_count: int,
                        hcount: int, hoff: int, lcount: int, loff: int,
                        bcount: int, boff: int, total_size: int) -> bytes:
    return struct.pack(
        ">hhH hh i hi hi hi h i",
        hdr.get("version", 3),
        hdr.get("type", 0),
        0,
        color_count, clut_count, ctab_off,
        hcount, hoff,
        lcount, loff,
        bcount, boff,
        hdr.get("pixels_to_world", 1),
        total_size,
    ) + b"\x00" * 506


def encode_collection(coll: dict) -> bytes:
    """Encode one parsed collection back to .shpA payload bytes.

    Layout per the M2 format (matches the reader in `parse_collection`)::

        [544 B cldf header — points to ctab/hlsh/llsh/bmap section starts]
        [color_count * clut_count * 8 B ctab data]
        [hlsh offset table (count * 4 B int32, each relative to collection start)]
        [hlsh record data — each (88 + 2*frames + 2) bytes]
        [llsh offset table (count * 4 B int32)]
        [llsh record data — each 36 B]
        [bmap offset table (count * 4 B int32)]
        [bmap record data — each padded to 4-byte boundary]
    """
    hdr = coll["header"]
    cluts = coll.get("cluts") or []
    high_shapes = coll.get("high_shapes") or []
    low_shapes = coll.get("low_shapes") or []
    bitmaps = coll.get("bitmaps") or []

    color_count = hdr.get("color_count", 256)
    clut_count = max(len(cluts), 1) if cluts else hdr.get("clut_count", 1)

    # Encode CLUTs — no offset table
    ctab_bytes = b"".join(_encode_clut(p, color_count) for p in cluts)

    # Encode each variable-size record as bytes; we'll build the offset table next
    hlsh_records = [
        _encode_high_shape_record(hs, hs.get("low_shape_indices") or [])
        if hs is not None else b""
        for hs in high_shapes
    ]
    llsh_records = [
        _encode_low_shape_record(ls) if ls is not None else b"\x00" * 36
        for ls in low_shapes
    ]
    bmap_records = [
        _encode_bitmap_payload_raw(bm) if bm is not None else b""
        for bm in bitmaps
    ]

    # Layout: header at 0, ctab data, then three (offset table + data) sections
    ctab_off = 544
    hlsh_table_off = ctab_off + len(ctab_bytes)
    hlsh_data_off = hlsh_table_off + 4 * len(hlsh_records)
    cur = hlsh_data_off
    hlsh_offsets = []
    for rec in hlsh_records:
        hlsh_offsets.append(cur)
        cur += len(rec)
    hlsh_data_size = cur - hlsh_data_off

    llsh_table_off = hlsh_data_off + hlsh_data_size
    llsh_data_off = llsh_table_off + 4 * len(llsh_records)
    cur = llsh_data_off
    llsh_offsets = []
    for rec in llsh_records:
        llsh_offsets.append(cur)
        cur += len(rec)
    llsh_data_size = cur - llsh_data_off

    bmap_table_off = llsh_data_off + llsh_data_size
    bmap_data_off = bmap_table_off + 4 * len(bmap_records)
    cur = bmap_data_off
    bmap_offsets = []
    for rec in bmap_records:
        bmap_offsets.append(cur)
        cur += len(rec)
    bmap_data_size = cur - bmap_data_off

    total_size = bmap_data_off + bmap_data_size

    hdr_bytes = _encode_cldf_header(
        hdr, ctab_off, color_count, clut_count,
        len(high_shapes), hlsh_table_off,
        len(low_shapes), llsh_table_off,
        len(bitmaps), bmap_table_off,
        total_size,
    )

    parts = [hdr_bytes, ctab_bytes]
    parts.append(b"".join(struct.pack(">i", o) for o in hlsh_offsets))
    parts.extend(hlsh_records)
    parts.append(b"".join(struct.pack(">i", o) for o in llsh_offsets))
    parts.extend(llsh_records)
    parts.append(b"".join(struct.pack(">i", o) for o in bmap_offsets))
    parts.extend(bmap_records)
    return b"".join(parts)


def write_m2(collections: list[dict], *, max_coll: int = 31) -> bytes:
    """Write an M2 / Infinity Shapes file from parsed-collection dicts.

    `collections` follows `parse_m2_collections()`'s structure. 16-bit slots
    are left empty (we only round-trip 8-bit data). The outer table is sized
    to fit `max(max_coll, max collection index)+1` entries.
    """
    coll_by_idx = {c["index"]: c for c in collections}
    real_max = max([max_coll] + [c["index"] for c in collections])
    table_size = (real_max + 1) * 32

    payloads: dict[int, bytes] = {
        idx: encode_collection(coll_by_idx[idx]) for idx in coll_by_idx
    }

    out = bytearray()
    file_off = table_size
    for idx in range(real_max + 1):
        coll = coll_by_idx.get(idx)
        if coll is not None and payloads.get(idx):
            status = coll.get("status", 0)
            flags = coll.get("flags", 0)
            off8 = file_off
            len8 = len(payloads[idx])
            file_off += len8
            out += struct.pack(">hHii ii", status, flags, off8, len8, -1, 0)
        else:
            out += struct.pack(">hHii ii", 0, 0, -1, 0, -1, 0)
        out += b"\x00" * 12
    for idx in sorted(coll_by_idx):
        out += payloads[idx]
    return bytes(out)
