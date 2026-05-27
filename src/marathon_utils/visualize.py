"""Top-down map renderer for Marathon scenarios.

A Pillow-based port of the essential subset of `mapxml2images.pl`. Reads
Map.scen directly (via marathon_utils.maps internals), then for each level
draws a top-down 2D PNG suitable for level-design review.

Output:
    <dest>/00_Arrival.png
    <dest>/01_Bigger Guns Nearby.png
    ...

Requires Pillow (`pip install Pillow`).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from . import macbinary, wad
from . import maps as maps_mod

# Object-type colors (matches Marathon's monster/scenery/item/sound type IDs)
_OBJ_COLORS = {
    0: (180, 80, 80),    # monster
    1: (90, 200, 90),    # scenery
    2: (220, 220, 80),   # item
    3: (90, 160, 220),   # player
    4: (180, 100, 200),  # goal
    5: (200, 200, 100),  # sound source
}


def _bbox(epnt: list[dict]) -> tuple[int, int, int, int]:
    xs = [p["x"] for p in epnt]
    ys = [p["y"] for p in epnt]
    return min(xs), min(ys), max(xs), max(ys)


def _color_for_floor(h: int, h_min: int, h_max: int) -> tuple[int, int, int]:
    """Map floor height to a grey shade (deeper sectors darker)."""
    if h_max == h_min:
        t = 0.5
    else:
        t = (h - h_min) / (h_max - h_min)
    v = int(60 + t * 140)  # 60..200
    return (v, v, v)


def render_level(level: dict, *, scale: float = 0.05, margin: int = 60,
                 max_dim: int = 2400, draw_objects: bool = True,
                 background: tuple[int, int, int] = (20, 20, 28)) -> Image.Image:
    """Render one level (dict produced by maps.parse_level) to a PIL Image.

    `scale` = pixels per Marathon world unit (int16 unit, i.e. WU * 1024).
    """
    epnt = level["data"].get("EPNT") or []
    lins = level["data"].get("LINS") or []
    poly = level["data"].get("POLY") or []
    objs = level["data"].get("OBJS") or []
    if not epnt:
        return Image.new("RGB", (320, 240), background)

    x0, y0, x1, y1 = _bbox(epnt)
    span_x = max(1, x1 - x0)
    span_y = max(1, y1 - y0)

    w = min(max_dim, int(span_x * scale) + margin * 2)
    h = min(max_dim, int(span_y * scale) + margin * 2)

    img = Image.new("RGB", (w, h), background)
    draw = ImageDraw.Draw(img, "RGBA")

    def to_px(mx: int, my: int) -> tuple[int, int]:
        px = margin + (mx - x0) * scale
        py = margin + (my - y0) * scale
        return int(px), int(py)

    # Floor-height range for shading
    fh = [p["floor_height"] for p in poly if p.get("vertex_count", 0) > 0]
    fh_min, fh_max = (min(fh), max(fh)) if fh else (0, 0)

    # Polygons (filled)
    for p in poly:
        if p.get("vertex_count", 0) < 3:
            continue
        pts = []
        for ei in p["endpoints"]:
            if 0 <= ei < len(epnt):
                pts.append(to_px(epnt[ei]["x"], epnt[ei]["y"]))
        if len(pts) >= 3:
            col = _color_for_floor(p["floor_height"], fh_min, fh_max)
            draw.polygon(pts, fill=(*col, 170))

    # Lines
    for ln in lins:
        e1, e2 = ln["endpoint1"], ln["endpoint2"]
        if 0 <= e1 < len(epnt) and 0 <= e2 < len(epnt):
            p1 = to_px(epnt[e1]["x"], epnt[e1]["y"])
            p2 = to_px(epnt[e2]["x"], epnt[e2]["y"])
            # Solid walls (no polygon on one side) get thicker, brighter ink
            solid = ln["cw_poly"] == -1 or ln["ccw_poly"] == -1
            color = (240, 240, 240) if solid else (160, 160, 175)
            width = 2 if solid else 1
            draw.line([p1, p2], fill=color, width=width)

    # Objects
    if draw_objects:
        for o in objs:
            color = _OBJ_COLORS.get(o["type"], (200, 80, 200))
            px, py = to_px(o["x"], o["y"])
            r = 3
            draw.ellipse([px - r, py - r, px + r, py + r],
                         fill=color, outline=(255, 255, 255))

    return img


def render_all_levels(source_path: Path | str, dest_dir: Path | str,
                      *, scale: float = 0.05, margin: int = 60,
                      max_dim: int = 2400) -> dict:
    """Render every level in Map.scen to its own PNG under dest_dir.

    Returns a manifest of what was written.
    """
    blob = Path(source_path).read_bytes()
    data_fork, _r, _m = macbinary.unwrap(blob)
    if data_fork is None:
        data_fork = blob
    hdr = wad.read_header(data_fork)
    directory = wad.read_directory(data_fork, hdr)

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for entry in directory:
        if entry["length"] == 0:
            continue
        level = maps_mod.parse_level(data_fork, entry, hdr)
        # Get the level name from Minf or NAME
        name = None
        if "Minf" in level["data"] and isinstance(level["data"]["Minf"], dict):
            name = level["data"]["Minf"].get("level_name")
        if not name and "NAME" in level["data"]:
            name = level["data"]["NAME"]
        if not name:
            name = f"Level_{entry['index']:02d}"
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()

        img = render_level(level, scale=scale, margin=margin, max_dim=max_dim)
        out_path = dest_dir / f"{entry['index']:02d}_{safe}.png"
        img.save(out_path)
        written.append({"index": entry["index"], "name": name,
                        "path": out_path.name, "size": img.size})

    return {"count": len(written), "levels": written}
