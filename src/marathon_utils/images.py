"""Marathon Images file decoder (`Images.imgA` / classic `Images`).

Decodes the chapter screens and title art that ship in the Aleph One Images
file. This is NOT part of the marathon-utils Perl script set (Hopper handles
PICTs in a separate `classic-mac-utils` repo) — it's a from-scratch QuickDraw
PICT v2 decoder targeting the opcodes Marathon actually uses.

The file is a Mac resource fork (parsed via `macrsrc`) holding `PICT` resources
(the images) and `clut` resources (shared palettes, generally unused since each
PICT embeds its own color table). Each PICT is a QuickDraw PICT v2 metafile.

Bitmap opcodes handled:

* `PackBitsRect`  (0x98) — 8-bit indexed, PackBits per row, embedded ColorTable
* `DirectBitsRect`(0x9A) — direct color:
    * packType 3, pixelSize 16 — RGB555, PackBits on 16-bit units
    * packType 4, pixelSize 32 — planar RGB (cmpCount 3), PackBits on bytes
* `BitsRect`      (0x90) — uncompressed indexed (defensive; not seen in M2/MI)

Requires Pillow.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

from PIL import Image

from . import macbinary, macrsrc

# ---------------------------------------------------------------------------
# PackBits
# ---------------------------------------------------------------------------

def unpack_bits(data: bytes, pos: int, n_units: int, unit_size: int) -> tuple[bytes, int]:
    """Decode PackBits into exactly `n_units` units of `unit_size` bytes.

    Returns (decoded_bytes, new_pos). Handles 1-byte units (indexed / planar
    direct color) and 2-byte units (16-bit direct color, packType 3).
    """
    out = bytearray()
    target = n_units * unit_size
    while len(out) < target and pos < len(data):
        flag = data[pos]
        pos += 1
        if flag < 128:  # 0..127: copy (flag + 1) literal units
            count = flag + 1
            nbytes = count * unit_size
            out += data[pos: pos + nbytes]
            pos += nbytes
        elif flag > 128:  # 129..255 => repeat next unit (257 - flag) times
            count = 257 - flag
            unit = data[pos: pos + unit_size]
            pos += unit_size
            out += unit * count
        # flag == 128: no-op
    return bytes(out[:target]), pos


# ---------------------------------------------------------------------------
# PixMap header
# ---------------------------------------------------------------------------

_PIXMAP_HEADER = 46  # rowBytes(2)+bounds(8)+pmVersion(2)+packType(2)+packSize(4)
#                      +hRes(4)+vRes(4)+pixelType(2)+pixelSize(2)+cmpCount(2)
#                      +cmpSize(2)+planeBytes(4)+pmTable(4)+pmReserved(4)


def _parse_pixmap(data: bytes, pos: int) -> dict:
    rb = struct.unpack(">H", data[pos: pos + 2])[0]
    row_bytes = rb & 0x3FFF
    top, left, bottom, right = struct.unpack(">hhhh", data[pos + 2: pos + 10])
    pack_type = struct.unpack(">h", data[pos + 12: pos + 14])[0]
    pixel_size = struct.unpack(">h", data[pos + 28: pos + 30])[0]
    cmp_count = struct.unpack(">h", data[pos + 30: pos + 32])[0]
    cmp_size = struct.unpack(">h", data[pos + 32: pos + 34])[0]
    return {
        "row_bytes": row_bytes,
        "bounds": (top, left, bottom, right),
        "width": right - left,
        "height": bottom - top,
        "pack_type": pack_type,
        "pixel_size": pixel_size,
        "cmp_count": cmp_count,
        "cmp_size": cmp_size,
        "next": pos + _PIXMAP_HEADER,
    }


def _parse_color_table(data: bytes, pos: int) -> tuple[list[tuple[int, int, int]], int]:
    """Parse a QuickDraw ColorTable. Returns (palette[256], new_pos)."""
    ct_flags = struct.unpack(">H", data[pos + 4: pos + 6])[0]
    ct_size = struct.unpack(">h", data[pos + 6: pos + 8])[0]  # entries - 1
    pos += 8
    palette: list[tuple[int, int, int]] = [(0, 0, 0)] * 256
    device = bool(ct_flags & 0x8000)
    for i in range(ct_size + 1):
        value = struct.unpack(">H", data[pos: pos + 2])[0]
        r = struct.unpack(">H", data[pos + 2: pos + 4])[0] >> 8
        g = struct.unpack(">H", data[pos + 4: pos + 6])[0] >> 8
        b = struct.unpack(">H", data[pos + 6: pos + 8])[0] >> 8
        pos += 8
        slot = i if device else value
        if 0 <= slot < 256:
            palette[slot] = (r, g, b)
    return palette, pos


def _read_row_count(data: bytes, pos: int, row_bytes: int) -> tuple[int, int]:
    """Read the per-row PackBits byte count (1 byte if rowBytes<=250 else 2)."""
    if row_bytes > 250:
        n = struct.unpack(">H", data[pos: pos + 2])[0]
        return n, pos + 2
    return data[pos], pos + 1


# ---------------------------------------------------------------------------
# Bitmap-opcode decoders
# ---------------------------------------------------------------------------

def _decode_indexed(data: bytes, pos: int, *, packbits: bool) -> Image.Image:
    """Decode PackBitsRect (0x98) / BitsRect (0x90): 8-bit indexed."""
    pm = _parse_pixmap(data, pos)
    pos = pm["next"]
    palette, pos = _parse_color_table(data, pos)
    pos += 8 + 8 + 2  # srcRect, dstRect, mode
    width, height, row_bytes = pm["width"], pm["height"], pm["row_bytes"]

    img = Image.new("RGB", (width, height))
    px = img.load()
    for y in range(height):
        if packbits and row_bytes >= 8:
            count, pos = _read_row_count(data, pos, row_bytes)
            row, _ = unpack_bits(data, pos, width, 1)
            pos += count
        else:
            row = data[pos: pos + width]
            pos += row_bytes
        for x in range(min(width, len(row))):
            px[x, y] = palette[row[x]]
    return img


def _decode_direct(data: bytes, pos: int) -> Image.Image:
    """Decode DirectBitsRect (0x9A): 16-bit RGB555 or 32-bit planar RGB."""
    pos += 4  # skip baseAddr (0x000000FF)
    pm = _parse_pixmap(data, pos)
    pos = pm["next"]
    pos += 8 + 8 + 2  # srcRect, dstRect, mode
    width, height = pm["width"], pm["height"]
    row_bytes = pm["row_bytes"]
    pack_type = pm["pack_type"]
    pixel_size = pm["pixel_size"]

    img = Image.new("RGB", (width, height))
    px = img.load()

    for y in range(height):
        if pixel_size == 16 and pack_type == 3:
            count, pos = _read_row_count(data, pos, row_bytes)
            row, _ = unpack_bits(data, pos, width, 2)
            pos += count
            for x in range(width):
                v = (row[x * 2] << 8) | row[x * 2 + 1]
                r = (v >> 10) & 0x1F
                g = (v >> 5) & 0x1F
                b = v & 0x1F
                px[x, y] = (r * 255 // 31, g * 255 // 31, b * 255 // 31)
        elif pixel_size == 32 and pack_type == 4:
            cmp_count = pm["cmp_count"]  # 3 (RGB) or 4 (ARGB)
            count, pos = _read_row_count(data, pos, row_bytes)
            row, _ = unpack_bits(data, pos, width * cmp_count, 1)
            pos += count
            # Planar: [R0..Rw][G0..Gw][B0..Bw] (skip alpha plane if cmp_count==4)
            base = (cmp_count - 3)  # 1 if alpha plane present, else 0
            rp = (base + 0) * width
            gp = (base + 1) * width
            bp = (base + 2) * width
            for x in range(width):
                px[x, y] = (row[rp + x], row[gp + x], row[bp + x])
        else:
            # Unpacked direct color (packType 0/1) — read row_bytes raw
            row = data[pos: pos + row_bytes]
            pos += row_bytes
            if pixel_size == 16:
                for x in range(width):
                    v = (row[x * 2] << 8) | row[x * 2 + 1]
                    r = (v >> 10) & 0x1F
                    g = (v >> 5) & 0x1F
                    b = v & 0x1F
                    px[x, y] = (r * 255 // 31, g * 255 // 31, b * 255 // 31)
            else:  # 32-bit chunky xRGB
                for x in range(width):
                    o = x * 4
                    px[x, y] = (row[o + 1], row[o + 2], row[o + 3])
    return img


# ---------------------------------------------------------------------------
# Opcode walker → image
# ---------------------------------------------------------------------------

def decode_pict(pict: bytes) -> Image.Image:
    """Decode a QuickDraw PICT v2 resource to an RGB Pillow image.

    Raises ValueError if no supported bitmap opcode is found.
    """
    if len(pict) < 10:
        raise ValueError("PICT too short")
    pos = 10  # skip 2-byte size + 8-byte frame rect

    def u16(o: int) -> int:
        return struct.unpack(">H", pict[o: o + 2])[0]

    safety = 0
    while pos < len(pict) and safety < 64:
        safety += 1
        op = u16(pos)
        pos += 2
        if op == 0x0011:        # VersionOp
            pos += 2
        elif op == 0x0C00:      # HeaderOp
            pos += 24
        elif op in (0x0000, 0x001E):  # NOP / DefHilite
            pass
        elif op in (0x001A, 0x001B, 0x001C):  # RGBFgCol / RGBBkCol / HiliteColor
            pos += 6
        elif op == 0x0001:      # Clip: region (u16 size, includes the size word)
            rsize = u16(pos)
            pos += rsize
        elif op == 0x00A0:      # ShortComment
            pos += 2
        elif op == 0x00A1:      # LongComment: kind(2) + size(2) + data
            pos += 2
            csize = u16(pos)
            pos += 2 + csize
        elif op in (0x0090, 0x0098):  # BitsRect / PackBitsRect (indexed)
            return _decode_indexed(pict, pos, packbits=(op == 0x0098))
        elif op == 0x009A:      # DirectBitsRect
            return _decode_direct(pict, pos)
        elif op == 0x00FF:      # OpEndPic
            break
        else:
            raise ValueError(f"unhandled PICT opcode 0x{op:04x} at offset {pos - 2}")
    raise ValueError("no bitmap opcode found in PICT")


# ---------------------------------------------------------------------------
# Top-level extractor
# ---------------------------------------------------------------------------

def extract(source_path: Path | str, dest_dir: Path | str) -> dict:
    """Decode every PICT in an Images file to PNG under dest_dir.

    Output:
        <dest>/PICT_<id>.png
        <dest>/manifest.json
    """
    blob = Path(source_path).read_bytes()
    _data, rsrc, _meta = macbinary.unwrap(blob)
    if rsrc is None:
        rsrc = blob
    resources = macrsrc.parse(rsrc)

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    manifest: dict = {"count": 0, "errors": [], "images": []}
    for entry in resources.get("PICT", []):
        rid = entry["id"]
        try:
            img = decode_pict(entry["data"])
        except Exception as e:
            manifest["errors"].append({"id": rid, "error": str(e)})
            continue
        out_path = dest / f"PICT_{rid}.png"
        img.save(out_path)
        manifest["count"] += 1
        manifest["images"].append({
            "id": rid, "width": img.width, "height": img.height,
            "file": out_path.name,
        })

    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
