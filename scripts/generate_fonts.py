#!/usr/bin/env python3
"""Generate the bundled terminal bitmap fonts from a free OFL source font.

The terminal renderer (`marathon_utils.terminals`) draws text with a small
bitmap-font format originally shipped by marathon-utils as ASCII representations
of Courier. To keep this package self-contained and license-clean, we generate
our own equivalents from **Courier Prime** (SIL Open Font License) — a
Courier-metric-compatible free font — and bundle the generated `.txt` files.

The generated files match the classic metrics exactly (MT 10 2 0 11 0,
BB 10 12 0 -10 0, 7px monospace advance, 10x12 glyph box) so the renderer's
layout is unchanged; only the glyph shapes come from Courier Prime.

Usage:
    # Fetch the OFL source fonts (only needed to regenerate):
    #   https://github.com/google/fonts/tree/main/ofl/courierprime
    python scripts/generate_fonts.py <dir-with-CourierPrime-*.ttf>

Output: src/marathon_utils/fonts/{Courier12,CourierBold12,CourierItalic12,
CourierBoldItalic12}.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Classic metrics (from marathon-utils Courier12.txt) — keep these fixed so the
# renderer's positioning math is identical to the original.
ASCENT = 10
DESCENT = 2
LEADING = 0
MAXW = 11
BB_W = 10
BB_H = 12
BB_XOFF = 0
BB_YOFF = -10
ADVANCE = 7          # monospace advance width
CODEPOINTS = range(32, 256)  # Latin-1 printable range

# Source font (SIL OFL) -> output bitmap font name
FONTS = {
    "CourierPrime-Regular.ttf": "Courier12.txt",
    "CourierPrime-Bold.ttf": "CourierBold12.txt",
    "CourierPrime-Italic.ttf": "CourierItalic12.txt",
    "CourierPrime-BoldItalic.ttf": "CourierBoldItalic12.txt",
}

# Pixel size for rasterization. Tuned so Courier Prime fills the 10x12 box with
# the baseline at row ASCENT.
PIXEL_SIZE = 13
BASELINE_ROW = ASCENT  # row index of the glyph baseline within the BB_H box


def _render_glyph(font: ImageFont.FreeTypeFont, ch: str) -> list[list[bool]]:
    """Rasterize one character into a BB_W x BB_H boolean grid."""
    img = Image.new("L", (BB_W, BB_H), 0)
    draw = ImageDraw.Draw(img)
    # Pillow's anchor "ls" = left baseline; place baseline at BASELINE_ROW.
    try:
        draw.text((0, BASELINE_ROW), ch, fill=255, font=font, anchor="ls")
    except (ValueError, OSError):
        draw.text((0, BASELINE_ROW - ASCENT), ch, fill=255, font=font)
    px = img.load()
    return [[px[x, y] >= 128 for x in range(BB_W)] for y in range(BB_H)]


def _glyph_is_blank(grid: list[list[bool]]) -> bool:
    return not any(any(row) for row in grid)


def _emit_font(ttf_path: Path, out_path: Path) -> int:
    font = ImageFont.truetype(str(ttf_path), PIXEL_SIZE)
    lines: list[str] = [
        f"MT {ASCENT} {DESCENT} {LEADING} {MAXW} 0",
        f"BB {BB_W} {BB_H} {BB_XOFF} {BB_YOFF} 0",
    ]
    # Default/missing glyph (codepoint 0): a hollow box, like the classic font.
    lines.append(f"GM {ADVANCE} 0 {BB_H}")
    box = [[False] * BB_W for _ in range(BB_H)]
    for x in range(1, 6):
        box[2][x] = box[9][x] = True
    for y in range(2, 10):
        box[y][1] = box[y][5] = True
    lines += ["".join("*" if c else "." for c in row) for row in box]

    # Control codepoints the renderer expects to be present-but-blank.
    for cp in (0, 9, 13):
        if cp != 0:
            lines.append(f"GL {cp} {ADVANCE} 0 0")

    n = 0
    for cp in CODEPOINTS:
        ch = chr(cp)
        grid = _render_glyph(font, ch)
        if cp == 32 or _glyph_is_blank(grid):
            lines.append(f"GL {cp} {ADVANCE} 0 0")
        else:
            lines.append(f"GL {cp} {ADVANCE} 0 {BB_H}")
            lines += ["".join("*" if c else "." for c in row) for row in grid]
        n += 1
    out_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return n


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    src_dir = Path(argv[1])
    out_dir = Path(__file__).resolve().parents[1] / "src" / "marathon_utils" / "fonts"
    out_dir.mkdir(parents=True, exist_ok=True)
    for ttf_name, out_name in FONTS.items():
        ttf = src_dir / ttf_name
        if not ttf.is_file():
            print(f"ERROR: source font not found: {ttf}", file=sys.stderr)
            return 1
        count = _emit_font(ttf, out_dir / out_name)
        print(f"{out_name}: {count} glyphs from {ttf_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
