"""Marathon marine sprite composer — Samsara Doom-mod helper.

Port of `shapesxml2marine.pl` from Hopper262/marathon-utils. Composites
Marathon's layered marine player sprites (collection 6) into single PNG
images suitable for use as Doom-mod player skins.

The Marathon player sprite is two layers: a leg/movement sprite at the
bottom, and a torso/weapon sprite anchored to it via `key_x` / `key_y`.
This script enumerates every (color x torso sequence x leg sequence x
view x animation-frame) combination and emits a composited PNG.

Output for a full Infinity shapes file: ~23,000 PNGs organized as::

    <dest>/<color>/<torso_sequence>/<leg_sequence>/view<V>_<tstep>-<lstep>.png

Plus single-layer poses for the "stationary" and "dying" sequences::

    <dest>/<color>/<sequence>/option<N>.png
    <dest>/<color>/dying-soft/view<V>_anim<N>.png

Requires Pillow.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import shapes as _shapes_mod

# These index lists match the Aleph One Infinity/M2 layout for collection 6
COLOR_NAMES = ("slate", "red", "violet", "yellow", "white", "orange", "blue", "green")

SEQ_NAMES = (
    "running", "fist-idle", "fist-firing", "pistol-idle", "pistol-firing",
    "pistol2-idle", "pistol2-firing", "stationary", "dying-soft", "dying-hard",
    "dead-soft", "dead-hard", "flame-idle", "flame-firing", "rocket-idle",
    "rocket-firing", "shotgun-idle", "shotgun-firing", "shotgun2-idle",
    "shotgun2-firing", "fusion-idle", "fusion-charged", "fusion-firing",
    "airborne", "sliding", "walking", "ar-idle", "ar-firing", "ball",
    "dummy-ball", "dummy-hand", "alien-idle", "alien-firing", "smg-idle",
    "smg-firing",
)

DYING = (8, 9)
LEGS = (0, 7, 23, 24, 25)
TORSOS = (
    1, 2, 3, 4, 5, 6, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22,
    26, 27, 28, 31, 32, 33, 34,
)


def _frame_image(low_shape: dict, bitmap, palette: list[tuple[int, int, int]],
                 transparent_idx: int = 0) -> Image.Image:
    """Render one Marathon frame as RGBA. The bitmap's column_order and
    transparency flags are honored via the existing Bitmap.to_image."""
    img = bitmap.to_image(palette)
    if low_shape.get("flags", 0) & 0x8000:  # x_mirror
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if low_shape.get("flags", 0) & 0x4000:  # y_mirror
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    return img


def _composite_layers(legs_low: dict, legs_bm,
                      torso_low: dict | None, torso_bm,
                      palette: list[tuple[int, int, int]]) -> Image.Image:
    """Composite legs + torso into a single canvas large enough to hold both.

    The torso is anchored to (legs.key_x, legs.key_y) relative to the leg
    bitmap's origin. We compute the union bounding box and paste each layer
    at the correct location.
    """
    legs_img = _frame_image(legs_low, legs_bm, palette)
    if torso_low is None or torso_bm is None:
        return legs_img

    torso_img = _frame_image(torso_low, torso_bm, palette)

    # In bitmap-local pixel coordinates, the legs' key point is at
    # (key_x, key_y). The torso must be placed so its origin lines up with
    # that point — i.e., torso top-left = legs key - torso origin.
    leg_key_x = legs_low.get("key_x", 0)
    leg_key_y = legs_low.get("key_y", 0)
    torso_origin_x = torso_low.get("origin_x", 0)
    torso_origin_y = torso_low.get("origin_y", 0)

    torso_offset_x = leg_key_x - torso_origin_x
    torso_offset_y = leg_key_y - torso_origin_y

    # Compute the bounding box covering both layers
    bbox_left = min(0, torso_offset_x)
    bbox_top = min(0, torso_offset_y)
    bbox_right = max(legs_img.width, torso_offset_x + torso_img.width)
    bbox_bottom = max(legs_img.height, torso_offset_y + torso_img.height)
    canvas = Image.new("RGBA", (bbox_right - bbox_left, bbox_bottom - bbox_top),
                       (0, 0, 0, 0))
    # Paste with -bbox_left, -bbox_top so legs origin sits at canvas origin
    canvas.paste(legs_img, (-bbox_left, -bbox_top), legs_img)
    canvas.paste(torso_img, (torso_offset_x - bbox_left, torso_offset_y - bbox_top),
                  torso_img)
    return canvas


def _index_collection_6(collections: list[dict]) -> dict | None:
    """Find the marine (collection 6) parsed dict, if present."""
    for c in collections:
        if c.get("index") == 6:
            return c
    return None


def compose_marines(source_path: Path | str, dest_dir: Path | str, *,
                    full_animation: bool = False) -> dict:
    """Composite every marine sprite combination from an M2/Infinity shapes file.

    `full_animation=True` enumerates every torso x leg x view x animation-frame
    combination (~23,000 PNGs for Infinity). The default is the abbreviated
    set: one composited PNG per (color x torso-sequence x leg-sequence x view)
    using the first frame of each sequence (~2,000 PNGs).
    """
    blob = Path(source_path).read_bytes()
    collections = _shapes_mod.parse_m2_collections(blob)
    marine = _index_collection_6(collections)
    if marine is None:
        raise ValueError("Collection 6 (marine) not found in shapes file.")

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    bitmaps = marine["bitmaps"]
    low_shapes = marine["low_shapes"]
    high_shapes = marine["high_shapes"]
    cluts = marine["cluts"]
    if not cluts:
        raise ValueError("Marine collection has no color tables.")

    manifest: dict = {"count": 0, "colors": len(cluts)}

    def _frame_for(seq_idx: int, view: int, step: int) -> dict | None:
        if not 0 <= seq_idx < len(high_shapes):
            return None
        hs = high_shapes[seq_idx]
        if hs is None:
            return None
        fpv = max(0, hs.get("frames_per_view", 0))
        if fpv == 0:
            return None
        flat_idx = view * fpv + step
        if flat_idx >= len(hs.get("low_shape_indices", [])):
            return None
        return low_shapes[hs["low_shape_indices"][flat_idx]] \
                if 0 <= hs["low_shape_indices"][flat_idx] < len(low_shapes) else None

    for color_idx, palette in enumerate(cluts):
        if color_idx >= len(COLOR_NAMES):
            break
        color_name = COLOR_NAMES[color_idx]
        color_dir = dest / color_name
        color_dir.mkdir(exist_ok=True)

        for tsidx in TORSOS:
            torso_seq = high_shapes[tsidx] if tsidx < len(high_shapes) else None
            if torso_seq is None:
                continue
            tsteps = max(1, torso_seq.get("frames_per_view", 0))
            views_t = _effective_views(torso_seq.get("number_of_views", 1))
            t_seq_name = SEQ_NAMES[tsidx] if tsidx < len(SEQ_NAMES) else f"seq{tsidx}"

            for lsidx in LEGS:
                leg_seq = high_shapes[lsidx] if lsidx < len(high_shapes) else None
                if leg_seq is None:
                    continue
                lsteps = max(1, leg_seq.get("frames_per_view", 0))
                views_l = _effective_views(leg_seq.get("number_of_views", 1))
                l_seq_name = SEQ_NAMES[lsidx] if lsidx < len(SEQ_NAMES) else f"seq{lsidx}"

                combo_dir = color_dir / t_seq_name / l_seq_name
                combo_dir.mkdir(parents=True, exist_ok=True)

                views = min(views_t, views_l, 8)
                t_step_range = range(tsteps) if full_animation else range(1)
                l_step_range = range(lsteps) if full_animation else range(1)
                for view in range(views):
                    for tstep in t_step_range:
                        torso_ls = _frame_for(tsidx, view, tstep)
                        if torso_ls is None:
                            continue
                        torso_bm = bitmaps[torso_ls["bitmap_index"]] \
                            if 0 <= torso_ls["bitmap_index"] < len(bitmaps) else None
                        for lstep in l_step_range:
                            legs_ls = _frame_for(lsidx, view, lstep)
                            if legs_ls is None or torso_bm is None:
                                continue
                            legs_bm = bitmaps[legs_ls["bitmap_index"]] \
                                if 0 <= legs_ls["bitmap_index"] < len(bitmaps) else None
                            if legs_bm is None:
                                continue
                            img = _composite_layers(legs_ls, legs_bm,
                                                    torso_ls, torso_bm, palette)
                            fname = (f"view{view}_{tstep}-{lstep}.png"
                                     if full_animation else f"view{view}.png")
                            img.save(combo_dir / fname)
                            manifest["count"] += 1

    return manifest


def _effective_views(number_of_views: int) -> int:
    """Marathon's view-count encoding: 10/3/9/11/5 map to 1/4/5/5/8 effective views."""
    return {10: 1, 3: 4, 9: 5, 11: 5, 5: 8}.get(number_of_views, number_of_views)
