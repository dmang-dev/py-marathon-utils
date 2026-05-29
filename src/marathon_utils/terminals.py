"""Marathon terminal screen renderer.

Port of `termxml2images.pl` (terminals subfolder of Hopper262/marathon-utils).
Renders Marathon 2 / Infinity terminal screens as PNG images in their iconic
green-on-black classic Mac look — the in-game text screens that deliver the
story.

Input: parsed terminal data from `maps.parse_terminal()` (groupings + font
changes + text bytes).

Output: per-terminal PNG pages, named `<level>_s<term>[u|s|f]_p<page>.png`
matching the upstream Perl's convention.

This v0.1 supports the M2/Infinity compiled-terminal format. M1's
human-readable script format (stored in Marathon.appl's `term` resources) is
not yet rendered — those scripts would need a compiler step to produce the
binary groupings/font_changes structure that this renderer consumes.

Requires Pillow.

Configuration: classic terminal screen layout is 320 logical px tall * 640
wide; the output PNG width can be larger (the canvas is rendered at 640 and
scaled at the end).
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Default classic-mode config (the values from config.ph)
# ---------------------------------------------------------------------------

CLASSIC_SCREEN = {"x": 0,   "y": 0,   "w": 640, "h": 320}
CLASSIC_RECTS = {
    "screen":        {"x": 0,   "y": 0,   "w": 640, "h": 320},
    "header":        {"x": 0,   "y": 0,   "w": 640, "h": 18},
    "footer":        {"x": 0,   "y": 302, "w": 640, "h": 18},
    "full_text":     {"x": 72,  "y": 27,  "w": 496, "h": 266},
    "left":          {"x": 9,   "y": 27,  "w": 307, "h": 266},
    "right":         {"x": 324, "y": 27,  "w": 307, "h": 266},
    "logon_graphic": {"x": 9,   "y": 27,  "w": 622, "h": 266},
}
CLASSIC_BG = (0, 0, 0)
CLASSIC_BORDER_BG = (38, 0, 0)        # (10000/65535) * 255 ~= 38
CLASSIC_BORDER_TEXT = (255, 0, 0)
CLASSIC_TEXT_COLORS = [
    (0,   255, 0),       # 0 — Green (default)
    (255, 255, 255),     # 1 — White
    (255, 0,   0),       # 2 — Red
    (0,   155, 0),       # 3 — Dim green (40000/65535)
    (0,   176, 200),     # 4 — Cyan-ish
    (255, 231, 0),       # 5 — Amber
    (175, 0,   0),       # 6 — Dim red (45000/65535)
    (12,  0,   255),     # 7 — Blue (3084/65535 for red)
]
CLASSIC_STRINGS = {
    "marathon_name": "U.E.S.C. Marathon",
    "starting_up":   "Opening Connection to \xa7.4.5-23",
    "manufacturer":  "CAS.qterm//CyberAcme Systems Inc.",
    "address":       "<931.461.60231.14.vt920>",
    "terminal":      "UESCTerm 802.11 (remote override)",
    "scrolling":     "PgUp/PgDown/Arrows To Scroll",
    "ack":           "Return/Enter To Acknowledge",
    "disconnecting": "Disconnecting...",
    "terminated":    "Connection Terminated.",
}

# Only these group types render to PNG; everything else is metadata or
# unsupported in v0.1.
_RENDERED_GROUP_TYPES = {"logon", "logoff", "information", "checkpoint", "pict"}

# Status modifier groups — they set the screen status for the next renderable
# group rather than producing their own page.
_STATUS_GROUP_TYPES = {"unfinished": "u", "success": "s", "failure": "f"}


# ---------------------------------------------------------------------------
# Bitmap font loader
# ---------------------------------------------------------------------------

class BitmapFont:
    """A Marathon-style bitmap font loaded from the `terminals/fonts/*.txt` format.

    `MT ascent descent leading maxw 0`  → global metrics
    `BB w h xoff yoff 0`                → bounding box; xoff is per-glyph left bearing
    `GM width 0 rowcount`               → default (codepoint 0) glyph
    `GL codepoint width 0 rowcount`     → glyph at codepoint; rowcount==0 means blank
        rowcount rows of '*' (set) and '.' (clear), each row is the bitmap width chars
    """

    __slots__ = (
        "ascent",
        "bb_h",
        "bb_w",
        "bb_xoff",
        "descent",
        "glyphs",
        "height",
        "leading",
        "offset",
    )

    def __init__(self) -> None:
        self.ascent = 10
        self.descent = 2
        self.leading = 0
        self.height = 12
        self.offset = 10
        self.bb_w = 10
        self.bb_h = 12
        self.bb_xoff = 0
        # glyphs[codepoint] = {"width": int, "pixels": list[list[bool]] or None}
        # Codepoint 0 is the default/missing-glyph fallback.
        self.glyphs: dict[int, dict] = {}

    @classmethod
    def load(cls, path: str | Path) -> BitmapFont:
        font = cls()
        lines = Path(path).read_text(encoding="ascii").splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if not line:
                continue
            parts = line.split()
            tag = parts[0]
            if tag == "MT":
                font.ascent = int(parts[1])
                font.descent = int(parts[2])
                font.leading = int(parts[3])
                font.height = font.ascent + font.descent + font.leading
                font.offset = font.ascent
            elif tag == "BB":
                font.bb_w = int(parts[1])
                font.bb_h = int(parts[2])
                font.bb_xoff = int(parts[3])
            elif tag == "GM":
                # Default glyph (codepoint 0). Format: GM width 0 rowcount
                width = int(parts[1])
                rowcount = int(parts[3])
                pixels = font._read_pixels(lines, i, rowcount, font.bb_w)
                i += rowcount
                font.glyphs[0] = {"width": width, "pixels": pixels}
            elif tag == "GL":
                # GL codepoint width 0 rowcount
                codepoint = int(parts[1])
                width = int(parts[2])
                rowcount = int(parts[4])
                if rowcount > 0:
                    pixels = font._read_pixels(lines, i, rowcount, font.bb_w)
                    i += rowcount
                else:
                    pixels = None
                font.glyphs[codepoint] = {"width": width, "pixels": pixels}
        return font

    @staticmethod
    def _read_pixels(lines: list[str], start: int, count: int, width: int) -> list[list[bool]]:
        out: list[list[bool]] = []
        for r in range(count):
            row_str = lines[start + r] if start + r < len(lines) else ""
            row = [c == "*" for c in row_str[:width]]
            while len(row) < width:
                row.append(False)
            out.append(row)
        return out

    def glyph(self, codepoint: int) -> dict:
        return self.glyphs.get(codepoint, self.glyphs.get(0, {"width": 7, "pixels": None}))

    def char_width(self, codepoint: int) -> int:
        return self.glyph(codepoint)["width"]


# ---------------------------------------------------------------------------
# Style runs from M2 font_changes
# ---------------------------------------------------------------------------

def styled_runs_for_group(group: dict, font_changes: list[dict]) -> list[dict]:
    """Compute a list of style-run dicts for one grouping's text slice.

    Each run = {"start": int (offset relative to group), "text": str,
                "font_index": int, "underline": bool, "color": int}.

    The font_changes list is whole-terminal; we filter to those whose
    change_index lies within the grouping's [start, start+length) window.
    """
    g_start = group["start_index"]
    g_end = g_start + group["length"]
    # Filter active style changes within this group
    rel_changes = [
        {**fc, "rel": fc["change_index"] - g_start}
        for fc in font_changes
        if g_start <= fc["change_index"] < g_end
    ]
    rel_changes.sort(key=lambda c: c["rel"])

    # If no style change at relative offset 0, prepend a default-style entry
    if not rel_changes or rel_changes[0]["rel"] > 0:
        rel_changes.insert(0, {"rel": 0, "font_index": 0, "underline": False, "color": 0})

    runs: list[dict] = []
    # Slice text into runs between consecutive change_index values
    text = group["_text"]   # caller pre-slices the group's text
    for i, change in enumerate(rel_changes):
        start = change["rel"]
        end = rel_changes[i + 1]["rel"] if i + 1 < len(rel_changes) else len(text)
        if start >= end:
            continue
        runs.append({
            "start": start,
            "text": text[start:end],
            "font_index": change.get("font_index", 0),
            "underline": change.get("underline", False),
            "color": change.get("color", 0),
        })
    return runs


# ---------------------------------------------------------------------------
# Line break + greedy wrap
# ---------------------------------------------------------------------------

_WRAP_BREAK_CHARS = (" ", "-", "<", "*")


def scrub_lines(lines: list[list[dict]]) -> list[list[dict]]:
    """Strip trailing whitespace from each line; drop trailing all-empty lines."""
    cleaned = []
    for runs in lines:
        # Drop pure-whitespace tail from the last run
        while runs and runs[-1]["text"].rstrip(" ") != runs[-1]["text"]:
            runs[-1] = {**runs[-1], "text": runs[-1]["text"].rstrip(" ")}
            if not runs[-1]["text"]:
                runs.pop()
            else:
                break
        cleaned.append(runs)
    # Drop trailing empty lines
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return cleaned


def split_lines(runs: list[dict]) -> list[list[dict]]:
    """Split a flat style-run list on \\r into a list of lines.

    Each output line is a list of run dicts. \\t is mapped to a single space.
    """
    lines: list[list[dict]] = [[]]
    for run in runs:
        text = run["text"].replace("\t", " ")
        parts = text.split("\r")
        for i, part in enumerate(parts):
            if part:
                lines[-1].append({**run, "text": part})
            if i + 1 < len(parts):
                lines.append([])
    return lines


def wrap_line_monospace(line_runs: list[dict], max_chars: int) -> list[list[dict]]:
    """Greedy monospace soft-wrap on the four classic break characters.

    Returns a list of new lines. Splits style runs when wrap points fall inside
    them, preserving the style attrs on the right half.
    """
    if max_chars <= 0:
        return [line_runs]

    # Build a flat (char, style_dict) sequence so we can scan break points easily.
    chars: list[tuple[str, dict]] = []
    for run in line_runs:
        for ch in run["text"]:
            chars.append((ch, run))
    if not chars:
        return [line_runs]
    if len(chars) <= max_chars:
        return [line_runs]

    out: list[list[dict]] = []
    i = 0
    while i < len(chars):
        end = min(i + max_chars, len(chars))
        if end < len(chars):
            # Walk back to the last break char
            split = end
            while split > i and chars[split - 1][0] not in _WRAP_BREAK_CHARS:
                split -= 1
            if split == i:
                split = end  # no break found — hard cut
        else:
            split = end
        segment = chars[i:split]
        # Rebuild runs from the segment, merging consecutive same-style chars
        line_out: list[dict] = []
        for ch, style in segment:
            if line_out and line_out[-1] is style:  # unlikely — different dicts
                line_out[-1]["text"] += ch
            elif line_out and _same_style(line_out[-1], style):
                line_out[-1] = {**line_out[-1], "text": line_out[-1]["text"] + ch}
            else:
                line_out.append({**style, "text": ch})
        out.append(line_out)
        # Skip leading spaces on next wrapped segment (post-break trim)
        j = split
        while j < len(chars) and chars[j][0] == " ":
            j += 1
        i = j
    return out


def _same_style(a: dict, b: dict) -> bool:
    return (a.get("font_index") == b.get("font_index")
            and a.get("underline") == b.get("underline")
            and a.get("color") == b.get("color"))


# ---------------------------------------------------------------------------
# Drawing primitives
# ---------------------------------------------------------------------------

def _draw_text_line(img: Image.Image, x: int, y: int, runs: list[dict],
                    fonts: list[BitmapFont], colors: list[tuple[int, int, int]]) -> int:
    """Render one line of styled runs onto `img` starting at (x,y). Returns the
    final x position after the line."""
    px = img.load()
    assert px is not None  # Pillow load() is never None for a real image
    img_w, img_h = img.size
    cx = x
    for run in runs:
        font = fonts[min(run["font_index"], len(fonts) - 1)]
        color = colors[run["color"] % len(colors)]
        baseline_y = y + font.offset
        text = run["text"]
        for ch in text:
            cp = ord(ch)
            g = font.glyph(cp)
            pixels = g["pixels"]
            w = g["width"]
            if pixels is not None:
                # Glyph bitmap is rendered at (cx + bb_xoff, y) per upstream
                ox = cx + font.bb_xoff
                oy = y
                for ry, row in enumerate(pixels):
                    for rx, on in enumerate(row):
                        if on and 0 <= ox + rx < img_w and 0 <= oy + ry < img_h:
                            px[ox + rx, oy + ry] = color
            cx += w
        if run.get("underline"):
            # Underline along the descender baseline
            uy = baseline_y + 2
            for ux in range(x, cx):
                if 0 <= ux < img_w and 0 <= uy < img_h:
                    px[ux, uy] = color
        x = cx  # next run continues
    return cx


def _wrap_to_rect(lines: list[list[dict]], rect: dict, font: BitmapFont,
                  char_width: int) -> list[list[list[dict]]]:
    """Wrap each source line to fit `rect.w`. Returns lines grouped into pages
    of `max_lines_per_page` each, where max_lines = rect.h / font.height."""
    max_chars = rect["w"] // char_width
    wrapped: list[list[dict]] = []
    for line_runs in lines:
        if not line_runs:
            wrapped.append([])
            continue
        wrapped.extend(wrap_line_monospace(line_runs, max_chars))

    max_lines = max(1, rect["h"] // font.height - 1)
    pages: list[list[list[dict]]] = []
    for i in range(0, max(1, len(wrapped)), max_lines):
        pages.append(wrapped[i: i + max_lines])
    return pages or [[]]


def _draw_text_block(img: Image.Image, rect: dict, page_lines: list[list[dict]],
                     fonts: list[BitmapFont], colors: list[tuple[int, int, int]]) -> None:
    """Draw a vertical block of styled lines clipped to rect."""
    primary = fonts[0]
    y = rect["y"] + 2
    for line_runs in page_lines:
        if line_runs:
            _draw_text_line(img, rect["x"], y, line_runs, fonts, colors)
        y += primary.height


def _draw_filled_rect(draw: ImageDraw.ImageDraw, rect: dict,
                      color: tuple[int, int, int]) -> None:
    draw.rectangle(
        [rect["x"], rect["y"], rect["x"] + rect["w"] - 1, rect["y"] + rect["h"] - 1],
        fill=color,
    )


# ---------------------------------------------------------------------------
# Default font set discovery
# ---------------------------------------------------------------------------

def default_fonts_dir() -> Path | None:
    """Locate the bundled Courier bitmap fonts.

    These ship inside the package (`marathon_utils/fonts/`), generated from the
    SIL-OFL Courier Prime font (see scripts/generate_fonts.py). Returns None
    only if the package data somehow wasn't installed.
    """
    bundled = Path(__file__).resolve().parent / "fonts"
    if bundled.is_dir() and (bundled / "Courier12.txt").is_file():
        return bundled
    return None


def load_default_fonts(fonts_dir: Path | None = None) -> list[BitmapFont]:
    fonts_dir = fonts_dir or default_fonts_dir()
    if fonts_dir is None:
        raise FileNotFoundError(
            "Could not find the bundled Courier bitmap fonts "
            "(marathon_utils/fonts/). Reinstall the package, or pass "
            "fonts_dir explicitly."
        )
    return [
        BitmapFont.load(fonts_dir / name) for name in (
            "Courier12.txt",
            "CourierBold12.txt",
            "CourierItalic12.txt",
            "CourierBoldItalic12.txt",
        )
    ]


# ---------------------------------------------------------------------------
# Page rendering — one PNG per page of one grouping
# ---------------------------------------------------------------------------

def _render_canvas(width: int = 640) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (CLASSIC_SCREEN["w"], CLASSIC_SCREEN["h"]), CLASSIC_BG)
    draw = ImageDraw.Draw(img)
    _draw_filled_rect(draw, CLASSIC_RECTS["screen"], CLASSIC_BG)
    _draw_filled_rect(draw, CLASSIC_RECTS["header"], CLASSIC_BORDER_BG)
    _draw_filled_rect(draw, CLASSIC_RECTS["footer"], CLASSIC_BORDER_BG)
    # Final scale to user width
    if width != CLASSIC_SCREEN["w"]:
        ratio = width / CLASSIC_SCREEN["w"]
        img = img.resize((width, int(CLASSIC_SCREEN["h"] * ratio)), Image.Resampling.NEAREST)
    return img, ImageDraw.Draw(img)


def _draw_header_footer(img: Image.Image, draw: ImageDraw.ImageDraw,
                        fonts: list[BitmapFont], level_name: str,
                        page_idx: int, total_pages: int) -> None:
    bold = fonts[min(1, len(fonts) - 1)]
    # Header: marathon_name centered
    header_text = CLASSIC_STRINGS["marathon_name"]
    hx = CLASSIC_RECTS["header"]["x"] + (CLASSIC_RECTS["header"]["w"]
                                         - len(header_text) * bold.char_width(ord("M"))) // 2
    hy = CLASSIC_RECTS["header"]["y"] + 4
    _draw_text_line(img, hx, hy,
                    [{"text": header_text, "font_index": 1,
                      "underline": False, "color": 0}],
                    fonts, [CLASSIC_BORDER_TEXT])
    # Footer: page indicator on the left, ack on the right
    if total_pages > 1:
        page_str = f"Page {page_idx + 1} of {total_pages}"
        _draw_text_line(img, CLASSIC_RECTS["footer"]["x"] + 8,
                        CLASSIC_RECTS["footer"]["y"] + 4,
                        [{"text": page_str, "font_index": 1,
                          "underline": False, "color": 0}],
                        fonts, [CLASSIC_BORDER_TEXT])


def _render_one_page(text_rect_lines: list[list[dict]],
                     rect: dict, fonts: list[BitmapFont],
                     colors: list[tuple[int, int, int]],
                     level_name: str, page_idx: int, total_pages: int,
                     picture: Image.Image | None = None,
                     picture_rect: dict | None = None) -> Image.Image:
    img, draw = _render_canvas(CLASSIC_SCREEN["w"])
    if picture and picture_rect:
        # Fit + center within rect preserving aspect
        target_w, target_h = picture_rect["w"], picture_rect["h"]
        pict = picture.copy()
        pict.thumbnail((target_w, target_h), Image.Resampling.NEAREST)
        px = picture_rect["x"] + (target_w - pict.width) // 2
        py = picture_rect["y"] + (target_h - pict.height) // 2
        img.paste(pict, (px, py))
    _draw_text_block(img, rect, text_rect_lines, fonts, colors)
    _draw_header_footer(img, draw, fonts, level_name, page_idx, total_pages)
    return img


def _load_picture(images_dir: Path | None, permutation: int) -> Image.Image | None:
    if images_dir is None or permutation < 0:
        return None
    for prefix_offset in (20000, 10000, 0):
        pid = permutation + prefix_offset
        for fmt in (f"PICT_{pid:05d}.png", f"{pid:05d}.png", f"PICT_{pid}.png"):
            p = images_dir / fmt
            if p.is_file():
                return Image.open(p).convert("RGB")
    return None


def render_terminal(terminal: dict, *, fonts: list[BitmapFont],
                    level_name: str = "",
                    images_dir: Path | None = None,
                    colors: list[tuple[int, int, int]] = CLASSIC_TEXT_COLORS,
                    ) -> list[tuple[str, Image.Image]]:
    """Render one terminal dict to a list of (suffix, Image) pairs.

    Suffix convention (matches the Perl `termxml2images.pl`)::

        [u|s|f]_p<N>   where the letter is the active status modifier
                       (none/unfinished/success/failure) and N is a page
                       counter that **continues across groupings** of the
                       same status within the terminal.

    Caller is responsible for prepending the terminal's identifier (level
    index + terminal index) to make the final filename unique.
    """
    out: list[tuple[str, Image.Image]] = []
    text = terminal["text"]
    status_suffix = ""
    # Page counter per status group ("" / "u" / "s" / "f")
    page_idx_by_status: dict[str, int] = {}

    for grouping in terminal.get("groupings", []):
        name = grouping["type_name"]
        if name in _STATUS_GROUP_TYPES:
            status_suffix = _STATUS_GROUP_TYPES[name]
            continue
        if name == "end":
            status_suffix = ""
            continue
        if name not in _RENDERED_GROUP_TYPES:
            continue

        # Slice the group's text out of the whole-terminal string. Index is in
        # MacRoman bytes but our text is already decoded; for ASCII-mostly
        # M2 terminal text the counts match.
        g_text = text[grouping["start_index"]: grouping["start_index"] + grouping["length"]]
        synth_group = {**grouping, "_text": g_text}
        flat_runs = styled_runs_for_group(synth_group, terminal.get("font_changes", []))
        if not flat_runs and g_text:
            flat_runs = [{"text": g_text, "font_index": 0,
                          "underline": False, "color": 0, "start": 0}]

        text_lines = split_lines(flat_runs)
        text_lines = scrub_lines(text_lines)

        picture: Image.Image | None = None
        picture_rect: dict | None = None
        if name in ("logon", "logoff"):
            text_rect = CLASSIC_RECTS["logon_graphic"]
            picture_rect = CLASSIC_RECTS["logon_graphic"]
            picture = _load_picture(images_dir, grouping["permutation"])
        elif name == "information":
            text_rect = CLASSIC_RECTS["full_text"]
        else:
            on_right = bool(grouping["flags"] & 0x1)
            text_rect = CLASSIC_RECTS["right"] if on_right else CLASSIC_RECTS["left"]
            picture_rect = CLASSIC_RECTS["left"] if on_right else CLASSIC_RECTS["right"]
            if name == "pict":
                picture = _load_picture(images_dir, grouping["permutation"])

        pages = _wrap_to_rect(text_lines, text_rect, fonts[0],
                              char_width=fonts[0].char_width(ord("M")))
        for page_lines in pages:
            page_n = page_idx_by_status.get(status_suffix, 0)
            page_idx_by_status[status_suffix] = page_n + 1
            img = _render_one_page(
                page_lines, text_rect, fonts, colors,
                level_name=level_name, page_idx=page_n, total_pages=0,
                picture=picture, picture_rect=picture_rect,
            )
            out.append((f"{status_suffix}_p{page_n}", img))
    return out


# ---------------------------------------------------------------------------
# M1 terminal script compiler
#
# M1 stores terminals as human-readable scripts inside Marathon.appl's `term`
# resources, e.g.:
#
#     ;L000.WELCOME.ENTRY
#     #logon
#     Airlock 34-a Terminal Access <Port 19.1.2.128>
#     ;
#     #information
#     <Message to All Marathon Terminals>
#     $BMarathon Emergency Systems Broadcast$b
#     ...
#     ;L000.WELCOME.SUCCESS
#     #information
#     ...
#
# We compile that into the same {groupings, font_changes, text} structure
# the M2/Infinity binary terminal format produces, so the same renderer
# can draw it.
# ---------------------------------------------------------------------------

_M1_DIRECTIVE_TO_GROUP = {
    "logon": "logon",
    "information": "information",
    "checkpoint": "checkpoint",
    "pict": "pict",
    "logoff": "logoff",
    "interlevel_teleport": "interlevel_teleport",
    "intralevel_teleport": "intralevel_teleport",
    "end": "end",
    "tag": "tag",
    "camera": "camera",
    "static": "static",
    "sound": "sound",
    "movie": "movie",
    "track": "track",
}

# Inline style commands per the Marathon engine convention
_INLINE_CMD = re.compile(r"\$([BIUbiuC])(\d?)")

_FACE_BOLD = 0x1
_FACE_ITALIC = 0x2
_FACE_UNDERLINE = 0x4


def _tokenize_m1_text(text: str) -> tuple[str, list[dict]]:
    """Parse inline `$B/$I/$U/$Cn` commands into a (plain_text, font_changes)
    pair. font_changes contains entries with `change_index` (byte offset into
    the plain text, MacRoman-encoded), `face`, `color`.
    """
    plain = []
    changes: list[dict] = []
    current_face = 0
    current_color = 0
    pos = 0

    def _emit_change(byte_offset: int):
        # Skip duplicate consecutive changes
        if changes and changes[-1]["change_index"] == byte_offset:
            changes[-1]["face"] = current_face
            changes[-1]["color"] = current_color
        else:
            changes.append({
                "change_index": byte_offset,
                "face": current_face,
                "color": current_color,
                "font_index": current_face & 0x3,
                "bold": bool(current_face & _FACE_BOLD),
                "italic": bool(current_face & _FACE_ITALIC),
                "underline": bool(current_face & _FACE_UNDERLINE),
            })

    for m in _INLINE_CMD.finditer(text):
        # Append text up to this command
        plain.append(text[pos:m.start()])
        cmd = m.group(1)
        arg = m.group(2)
        # Compute current byte offset in the rendered plain string
        flat = "".join(plain)
        byte_offset = len(flat.encode("mac-roman", errors="replace"))
        if cmd == "B":
            current_face |= _FACE_BOLD
        elif cmd == "b":
            current_face &= ~_FACE_BOLD
        elif cmd == "I":
            current_face |= _FACE_ITALIC
        elif cmd == "i":
            current_face &= ~_FACE_ITALIC
        elif cmd == "U":
            current_face |= _FACE_UNDERLINE
        elif cmd == "u":
            current_face &= ~_FACE_UNDERLINE
        elif cmd == "C" and arg.isdigit():
            current_color = int(arg)
        _emit_change(byte_offset)
        pos = m.end()
    plain.append(text[pos:])
    return "".join(plain), changes


def compile_m1_script(script: str) -> dict:
    """Compile an M1 script-format terminal into the M2-style structure that
    `render_terminal()` expects.

    Returns a dict with `flags`, `lines_per_page`, `groupings`, `font_changes`,
    `text` — same shape as `maps.parse_terminal` output.
    """
    # Normalize line endings (M1 uses classic Mac \r; strings module already
    # normalizes when loading from the appl resource fork, but be defensive)
    lines = script.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    # Status modifier mapping from section name suffix
    status_for_suffix = {"SUCCESS": "success", "FAILURE": "failure",
                          "UNFINISHED": "unfinished"}

    groupings: list[dict] = []
    font_changes: list[dict] = []
    text_parts: list[str] = []
    current_status: str | None = None
    pending_directive: tuple[str, int] | None = None
    pending_text: list[str] = []

    def flush_pending(text_start: int) -> int:
        """Emit the buffered pending directive + its text, return new text length."""
        if pending_directive is None:
            return text_start
        directive, permutation = pending_directive
        group_type_name = _M1_DIRECTIVE_TO_GROUP.get(directive, "information")
        body = "\n".join(pending_text).strip("\n")
        # Convert \n back to \r for the Marathon engine convention
        body_rendered, body_changes = _tokenize_m1_text(body.replace("\n", "\r"))
        body_bytes = body_rendered.encode("mac-roman", errors="replace")

        # Shift the body's font_changes to whole-terminal byte offsets
        for fc in body_changes:
            font_changes.append({**fc, "change_index": text_start + fc["change_index"]})

        groupings.append({
            "flags": 0,
            "type": _group_type_index(group_type_name),
            "type_name": group_type_name,
            "permutation": permutation,
            "start_index": text_start,
            "length": len(body_bytes),
            "max_lines": 0,
        })
        text_parts.append(body_rendered)
        return text_start + len(body_bytes)

    text_offset = 0
    for raw_line in lines:
        line = raw_line.rstrip("\r")

        if line.startswith(";L"):
            # Section marker: ;L<NNN>.<name>.<status>
            # Flush any pending directive that was being built
            text_offset = flush_pending(text_offset)
            pending_directive = None
            pending_text = []
            parts = line[1:].split(".")
            suffix = parts[-1].upper() if parts else ""
            new_status = status_for_suffix.get(suffix)
            if new_status and new_status != current_status:
                # Emit a status-modifier grouping with empty text
                groupings.append({
                    "flags": 0,
                    "type": _group_type_index(new_status),
                    "type_name": new_status,
                    "permutation": 0,
                    "start_index": text_offset,
                    "length": 0,
                    "max_lines": 0,
                })
                current_status = new_status
            elif suffix == "ENTRY" or not new_status:
                # Entry / default — emit `end` to clear any prior status
                if current_status is not None:
                    groupings.append({
                        "flags": 0,
                        "type": _group_type_index("end"),
                        "type_name": "end",
                        "permutation": 0,
                        "start_index": text_offset,
                        "length": 0,
                        "max_lines": 0,
                    })
                    current_status = None
            continue

        if line == ";":
            # In-section separator — flush current directive's body
            text_offset = flush_pending(text_offset)
            pending_directive = None
            pending_text = []
            continue

        if line.startswith("#"):
            # New directive — flush previous, start new
            text_offset = flush_pending(text_offset)
            cmd_parts = line[1:].split(None, 1)
            cmd = cmd_parts[0] if cmd_parts else ""
            perm = 0
            if len(cmd_parts) > 1:
                try:
                    perm = int(cmd_parts[1].strip())
                except ValueError:
                    perm = 0
            pending_directive = (cmd, perm)
            pending_text = []
            continue

        if pending_directive is not None:
            pending_text.append(raw_line)

    # Flush trailing pending content
    text_offset = flush_pending(text_offset)

    return {
        "flags": 0,
        "lines_per_page": 23,
        "groupings": groupings,
        "font_changes": font_changes,
        "text": "".join(text_parts),
    }


def _group_type_index(name: str) -> int:
    from . import maps
    try:
        return maps.TERMINAL_GROUP_TYPES.index(name)
    except ValueError:
        return 4  # "information" fallback


# ---------------------------------------------------------------------------
# Terminal location finder (port of termxml2locations.pl)
#
# Walks a level's SIDS chunk looking for sides with the "control panel" flag
# set whose panel_type indicates a computer terminal. Returns world-space
# (x,y) coordinates suitable for plotting on a map view.
# ---------------------------------------------------------------------------

# panel_type index -> semantic name (M1)
_M1_PANEL_TYPES = (
    "oxygen_refuel", "shield_refuel", "double_shield_refuel",
    "triple_shield_refuel", "light_switch", "platform_switch",
    "pattern_buffer", "tag_switch", "computer_terminal", "tag_switch",
    "double_shield_refuel", "triple_shield_refuel", "platform_switch",
    "pattern_buffer",
)

# M2/Infinity: 5 banks of 11 panels, panel_type = bank * 11 + index_in_bank
_M2_PANEL_BASE = (
    "oxygen_refuel", "shield_refuel", "double_shield_refuel", "tag_switch",
    "light_switch", "platform_switch", "tag_switch", "pattern_buffer",
    "computer_terminal", "tag_switch", "tag_switch",
)


def _panel_name(panel_type: int, is_m1: bool) -> str:
    if is_m1:
        if 0 <= panel_type < len(_M1_PANEL_TYPES):
            return _M1_PANEL_TYPES[panel_type]
        return "unknown"
    base = panel_type % 11
    return _M2_PANEL_BASE[base] if 0 <= base < len(_M2_PANEL_BASE) else "unknown"


def terminal_locations(level: dict, *, is_m1: bool) -> list[dict]:
    """Find all `computer_terminal` panels in a parsed level.

    `level` is a dict from `maps.parse_level()`. Returns a list of dicts
    with the terminal's world position::

        [{"poly": <int>, "line": <int>, "x": <int>, "y": <int>,
          "panel_perm": <int>, "panel_type": <int>}, ...]

    The `x`/`y` are in Marathon world units (int16 * 1024-fixed).
    """
    sides = level["data"].get("SIDS") or []
    epnt = level["data"].get("EPNT") or []
    lins = level["data"].get("LINS") or []
    out = []
    for s in sides:
        # SIDS flag 0x2 = "is a control panel"
        if not (s["flags"] & 0x2):
            continue
        name = _panel_name(s["panel_type"], is_m1)
        if name != "computer_terminal":
            continue
        # Use the line's midpoint as the terminal's position
        line_idx = s["line_index"]
        if not 0 <= line_idx < len(lins):
            continue
        ln = lins[line_idx]
        e1, e2 = ln["endpoint1"], ln["endpoint2"]
        if not (0 <= e1 < len(epnt) and 0 <= e2 < len(epnt)):
            continue
        mid_x = (epnt[e1]["x"] + epnt[e2]["x"]) // 2
        mid_y = (epnt[e1]["y"] + epnt[e2]["y"]) // 2
        out.append({
            "poly": s["poly_index"],
            "line": line_idx,
            "x": mid_x, "y": mid_y,
            "panel_perm": s["panel_perm"],
            "panel_type": s["panel_type"],
        })
    return out


# ---------------------------------------------------------------------------
# HTML preview (port of html_preview.pl)
# ---------------------------------------------------------------------------

def generate_html_preview(images_dir: Path | str, *,
                          scenario_name: str = "Marathon",
                          level_names: list[str] | None = None) -> str:
    """Write an `index.html` file into `images_dir` that displays every
    rendered terminal page grouped by level.

    Looks for PNGs named `<level>_s<term>[u|s|f]_p<page>.png` (the convention
    used by `extract()` and `render_terminal()`).

    Returns the absolute path to the generated index.html.
    """
    images_dir = Path(images_dir)
    pngs = sorted(images_dir.glob("*.png"))
    # Group by level prefix
    by_level: dict[int, list[Path]] = {}
    for p in pngs:
        try:
            level_idx = int(p.stem.split("_", 1)[0])
        except ValueError:
            continue
        by_level.setdefault(level_idx, []).append(p)

    html: list[str] = ['<!DOCTYPE html>', '<html lang="en"><head>',
                       f'<title>{_html_escape(scenario_name)} Terminals</title>',
                       '<meta charset="utf-8">',
                       '<style>',
                       'body { background:#000; color:#0f0; font-family:monospace; }',
                       'h2 { border-bottom:1px solid #0f0; padding-bottom:4px; }',
                       '.term { border:1px solid #333; padding:8px; margin:12px 0;',
                       '         display:inline-block; vertical-align:top; }',
                       '.term img { display:block; image-rendering:pixelated;',
                       '             max-width: 640px; }',
                       '</style></head><body>',
                       f'<h1>{_html_escape(scenario_name)} Terminals</h1>']

    for level_idx in sorted(by_level):
        title = (level_names[level_idx]
                 if level_names and level_idx < len(level_names)
                 else f"Level {level_idx}")
        html.append(f'<h2 id="level-{level_idx}">{level_idx}. {_html_escape(title)}</h2>')
        for p in by_level[level_idx]:
            rel = p.name
            html.append(f'<div class="term"><img src="{_html_escape(rel)}" '
                         f'alt="{_html_escape(rel)}"></div>')
    html.append('</body></html>')

    out = images_dir / "index.html"
    out.write_text("\n".join(html), encoding="utf-8")
    return str(out)


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


# ---------------------------------------------------------------------------
# Top-level: render all terminals in one or more levels
# ---------------------------------------------------------------------------

def extract_m1(source_path: Path | str, dest_dir: Path | str, *,
               images_dir: Path | str | None = None,
               fonts_dir: Path | str | None = None,
               ) -> dict:
    """Render Marathon 1 terminals from a `Marathon.appl` resource fork.

    M1 stores terminals as human-readable scripts in `term` resources rather
    than compiled chunks in the level WAD. We extract those scripts, compile
    each with `compile_m1_script`, and render to PNG. Naming:
    `appl_term<resource-id>[u|s|f]_p<page>.png`.
    """
    from . import strings

    fonts = load_default_fonts(Path(fonts_dir) if fonts_dir else None)
    images = Path(images_dir) if images_dir else None

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    scripts = strings.extract(source_path).get("term", {})
    manifest: dict = {"terminals": [], "page_count": 0, "terminal_count": 0}
    for tid, script in sorted(scripts.items()):
        compiled = compile_m1_script(script)
        pages = render_terminal(compiled, fonts=fonts,
                                level_name=f"Terminal {tid}", images_dir=images)
        for suffix, img in pages:
            fname = f"appl_term{tid}{suffix}.png"
            img.save(dest_dir / fname)
            manifest["page_count"] += 1
        manifest["terminal_count"] += 1
        manifest["terminals"].append({"id": tid, "pages": len(pages)})
    return manifest


def extract(source_path: Path | str, dest_dir: Path | str, *,
            images_dir: Path | str | None = None,
            fonts_dir: Path | str | None = None,
            ) -> dict:
    """Render every terminal in `source_path` to PNG files under `dest_dir`.

    Auto-detects the Marathon version:

    * M2 / Infinity maps (`Map.sceA`) carry compiled `term` chunks in each
      level WAD — rendered directly.
    * Marathon 1 `Marathon.appl` carries human-readable terminal scripts in
      its resource fork — compiled, then rendered (delegates to `extract_m1`).

    Naming follows the upstream Perl convention:
    `<level>_s<N>[u|s|f]_p<page>.png` (M2/MI) or
    `appl_term<id>[u|s|f]_p<page>.png` (M1 appl).
    """
    from . import macbinary, macrsrc, maps, wad

    blob = Path(source_path).read_bytes()
    data, rsrc, _m = macbinary.unwrap(blob)

    # M1 detection: a resource fork containing script-format `term` resources.
    if rsrc:
        resources = macrsrc.parse(rsrc)
        m1_terms = [e for e in resources.get("term", [])
                    if e["data"][:1] in (b";", b"#")]
        if m1_terms:
            return extract_m1(source_path, dest_dir,
                              images_dir=images_dir, fonts_dir=fonts_dir)

    fonts = load_default_fonts(Path(fonts_dir) if fonts_dir else None)
    images = Path(images_dir) if images_dir else None

    payload = data if data is not None else blob
    hdr = wad.read_header(payload)
    directory = wad.read_directory(payload, hdr)

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict = {"levels": [], "page_count": 0, "terminal_count": 0}
    for entry in directory:
        if entry["length"] == 0:
            continue
        level = maps.parse_level(payload, entry, hdr)
        terms = level["data"].get("term", []) or []
        if isinstance(terms, dict) or not terms:
            continue
        level_name = (level["data"].get("Minf", {}) or {}).get("level_name") \
                      or f"Level_{entry['index']:02d}"
        for ti, term in enumerate(terms):
            pages = render_terminal(term, fonts=fonts, level_name=level_name,
                                    images_dir=images)
            for suffix, img in pages:
                # Full filename: <level>_s<terminal>[u|s|f]_p<page>.png
                fname = f"{entry['index']}_s{ti}{suffix}.png"
                img.save(dest_dir / fname)
                manifest["page_count"] += 1
            manifest["terminal_count"] += 1
        manifest["levels"].append({
            "index": entry["index"], "name": level_name,
            "terminals": len(terms),
        })
    return manifest
