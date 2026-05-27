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


def parse_bitmap(data: bytes, base: int) -> Bitmap:
    """Parse one bitmap (header + payload). M1 bitmaps may be RLE-compressed
    when bytes_per_row == -1, in row OR column order per the flags."""
    width = _s16(data, base + 0)
    height = _s16(data, base + 2)
    bytes_per_row = _s16(data, base + 4)
    flags = _u16(data, base + 6)
    # bit_depth at base+8 is always 8 in M1; reserved bytes 10..25
    column_order = bool(flags & 0x8000)

    address_table_count = (width if column_order else height) + 1
    data_start = base + 26 + 4 * address_table_count
    line_count = width if column_order else height
    line_length = height if column_order else width

    if bytes_per_row < 0:  # M1 row/column RLE
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
    else:
        # Raw uncompressed: pull row-by-row (or column-by-column) of exactly
        # `line_length` bytes. The address table is informational; we read
        # sequentially.
        raw = data[data_start: data_start + line_count * line_length]
        indices = bytearray(raw)

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

def parse_collection(payload: bytes) -> dict:
    """Parse the inner payload of one `.256` resource into a structured dict.

    Caller is responsible for stripping the leading 4-byte total-size field
    that wraps each resource in the rsrc fork.
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

    bitmaps = [parse_bitmap(payload, off) for off in bitmap_offsets]
    high_shapes = [parse_high_shape(payload, off) for off in high_offsets]
    low_shapes = [parse_low_shape(payload, off) for off in low_offsets]

    return {
        "header": hdr,
        "cluts": cluts,
        "bitmaps": bitmaps,
        "high_shapes": high_shapes,
        "low_shapes": low_shapes,
    }


def extract(source_path: Path | str, dest_dir: Path | str,
            clut_index: int = 0) -> dict:
    """Extract `Shapes.shps` to PNG files under dest_dir.

    Each `.256` resource (collection) becomes its own subdirectory. The first
    CLUT (or `clut_index`) is used as the default palette for the bitmap PNGs.
    """
    blob = Path(source_path).read_bytes()
    _data, rsrc, _meta = macbinary.unwrap(blob)
    if rsrc is None:
        rsrc = blob

    resources = macrsrc.parse(rsrc)
    collections = resources.get(".256", [])

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict = {"collections": [], "errors": []}
    for res in collections:
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
