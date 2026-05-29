"""Marathon physics model extractor.

Decodes the five M2/Infinity physics chunks:

    MNpx — monster definitions      (156 B/record)
    FXpx — effect definitions       (14 B/record)
    PRpx — projectile definitions   (48 B/record)
    PXpx — physics constants        (104 B/record)
    WPpx — weapon definitions       (134 B/record = 62 main + 2 * 36 triggers)

These chunks appear in three contexts:

1. **Standalone `Standard.phyA`** — a WAD file in `Physics Models/` that
   wraps all five chunks. Both M2 and Infinity ship one.
2. **Per-level embedded chunks** — Infinity stores per-level physics in the
   Map.sceA level WAD so scenarios can customize gameplay. The chunks use
   the same record layouts.
3. **M1 `Physics.phys`** — older format with a `mons` chunk that uses a
   slightly different (smaller) monster layout. Not fully decoded yet — we
   preserve the raw bytes and document the gap below.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

from . import macbinary, wad

# ---------------------------------------------------------------------------
# Byte readers
# ---------------------------------------------------------------------------

def _s16(b: bytes, off: int) -> int:
    return struct.unpack(">h", b[off: off + 2])[0]


def _u16(b: bytes, off: int) -> int:
    return struct.unpack(">H", b[off: off + 2])[0]


def _s32(b: bytes, off: int) -> int:
    return struct.unpack(">i", b[off: off + 4])[0]


def _u32(b: bytes, off: int) -> int:
    return struct.unpack(">I", b[off: off + 4])[0]


def _fixed(b: bytes, off: int) -> float:
    """Read a Mac/Bungie Fixed (16.16 signed). Returns float."""
    return _s32(b, off) / 65536.0


def _wd(b: bytes, off: int) -> float:
    """Read a Marathon WorldDistance (int16 / 1024). Returns float WU."""
    return _s16(b, off) / 1024.0


def _shape_desc(v: int) -> dict | None:
    """Decode a packed shape_descriptor uint16. Returns None for `0xFFFF`."""
    if v == 0xFFFF:
        return None
    return {
        "shape": v & 0xFF,
        "collection": (v >> 8) & 0x1F,
        "clut": (v >> 13) & 0x7,
        "raw": v,
    }


# ---------------------------------------------------------------------------
# MNpx — monster definitions (156 B)
# ---------------------------------------------------------------------------

MNPX_RECORD = 156


def parse_mnpx_record(d: bytes, off: int) -> dict:
    return {
        "collection": _s16(d, off + 0),
        "vitality": _s16(d, off + 2),
        "immunities": _u32(d, off + 4),
        "weaknesses": _u32(d, off + 8),
        "flags": _u32(d, off + 12),
        "class": _u32(d, off + 16),
        "friends": _u32(d, off + 20),
        "enemies": _u32(d, off + 24),
        "sound_pitch": _fixed(d, off + 28),
        "activation_sound": _s16(d, off + 32),
        "friendly_activation_sound": _s16(d, off + 34),
        "clear_sound": _s16(d, off + 36),
        "kill_sound": _s16(d, off + 38),
        "apology_sound": _s16(d, off + 40),
        "friendly_fire_sound": _s16(d, off + 42),
        "flaming_sound": _s16(d, off + 44),
        "random_sound": _s16(d, off + 46),
        "random_sound_mask": _u16(d, off + 48),
        "carrying_item_type": _s16(d, off + 50),
        "radius": _wd(d, off + 52),
        "height": _wd(d, off + 54),
        "preferred_hover_height": _wd(d, off + 56),
        "minimum_ledge_delta": _wd(d, off + 58),
        "maximum_ledge_delta": _wd(d, off + 60),
        "external_velocity_scale": _fixed(d, off + 62),
        "impact_effect": _s16(d, off + 66),
        "melee_impact_effect": _s16(d, off + 68),
        "contrail_effect": _s16(d, off + 70),
        "half_visual_arc": _s16(d, off + 72),
        "half_vertical_visual_arc": _s16(d, off + 74),
        "visual_range": _wd(d, off + 76),
        "dark_visual_range": _wd(d, off + 78),
        "intelligence": _s16(d, off + 80),
        "speed": _s16(d, off + 82),
        "gravity": _s16(d, off + 84),
        "terminal_velocity": _s16(d, off + 86),
        "door_retry_mask": _u16(d, off + 88),
        "shrapnel_radius": _s16(d, off + 90),
        "shrapnel_damage": {
            "type": _s16(d, off + 92),
            "flags": _u16(d, off + 94),
            "base": _s16(d, off + 96),
            "random": _s16(d, off + 98),
            "scale": _fixed(d, off + 100),
        },
        "hit_shape": _shape_desc(_u16(d, off + 104)),
        "hard_dying_shape": _shape_desc(_u16(d, off + 106)),
        "soft_dying_shape": _shape_desc(_u16(d, off + 108)),
        "hard_dead_shape": _shape_desc(_u16(d, off + 110)),
        "soft_dead_shape": _shape_desc(_u16(d, off + 112)),
        "stationary_shape": _shape_desc(_u16(d, off + 114)),
        "moving_shape": _shape_desc(_u16(d, off + 116)),
        "teleport_in_shape": _shape_desc(_u16(d, off + 118)),
        "teleport_out_shape": _shape_desc(_u16(d, off + 120)),
        "attack_frequency": _s16(d, off + 122),
        "melee_attack": {
            "type": _s16(d, off + 124),
            "repetitions": _s16(d, off + 126),
            "error": _s16(d, off + 128),
            "range": _wd(d, off + 130),
            "shape": _shape_desc(_u16(d, off + 132)),
            "dx": _wd(d, off + 134),
            "dy": _wd(d, off + 136),
            "dz": _wd(d, off + 138),
        },
        "ranged_attack": {
            "type": _s16(d, off + 140),
            "repetitions": _s16(d, off + 142),
            "error": _s16(d, off + 144),
            "range": _wd(d, off + 146),
            "shape": _shape_desc(_u16(d, off + 148)),
            "dx": _wd(d, off + 150),
            "dy": _wd(d, off + 152),
            "dz": _wd(d, off + 154),
        },
    }


# ---------------------------------------------------------------------------
# FXpx — effect definitions (14 B)
# ---------------------------------------------------------------------------

FXPX_RECORD = 14


def parse_fxpx_record(d: bytes, off: int) -> dict:
    return {
        "collection": _s16(d, off + 0),
        "shape": _s16(d, off + 2),
        "sound_pitch": _fixed(d, off + 4),
        "flags": _u16(d, off + 8),
        "delay": _s16(d, off + 10),
        "delay_sound": _s16(d, off + 12),
    }


# ---------------------------------------------------------------------------
# PRpx — projectile definitions (48 B)
# ---------------------------------------------------------------------------

PRPX_RECORD = 48


def parse_prpx_record(d: bytes, off: int) -> dict:
    return {
        "collection": _s16(d, off + 0),
        "shape": _s16(d, off + 2),
        "detonation_effect": _s16(d, off + 4),
        "media_detonation_effect": _s16(d, off + 6),
        "contrail_effect": _s16(d, off + 8),
        "ticks_between_contrails": _s16(d, off + 10),
        "maximum_contrails": _s16(d, off + 12),
        "media_projectile_promotion": _s16(d, off + 14),
        "radius": _wd(d, off + 16),
        "area_of_effect": _wd(d, off + 18),
        "damage": {
            "type": _s16(d, off + 20),
            "flags": _s16(d, off + 22),
            "base": _s16(d, off + 24),
            "random": _s16(d, off + 26),
            "scale": _fixed(d, off + 28),
        },
        "flags": _u32(d, off + 32),
        "speed": _wd(d, off + 36),
        "maximum_range": _wd(d, off + 38),
        "sound_pitch": _fixed(d, off + 40),
        "flyby_sound": _s16(d, off + 44),
        "rebound_sound": _s16(d, off + 46),
    }


# ---------------------------------------------------------------------------
# PXpx — player physics constants (104 B)
# ---------------------------------------------------------------------------

PXPX_RECORD = 104


def parse_pxpx_record(d: bytes, off: int) -> dict:
    return {
        "max_forward_velocity": _fixed(d, off + 0),
        "max_backward_velocity": _fixed(d, off + 4),
        "max_perpendicular_velocity": _fixed(d, off + 8),
        "acceleration": _fixed(d, off + 12),
        "deceleration": _fixed(d, off + 16),
        "airborne_deceleration": _fixed(d, off + 20),
        "gravitational_acceleration": _fixed(d, off + 24),
        "climbing_acceleration": _fixed(d, off + 28),
        "terminal_velocity": _fixed(d, off + 32),
        "external_deceleration": _fixed(d, off + 36),
        "angular_acceleration": _fixed(d, off + 40),
        "angular_deceleration": _fixed(d, off + 44),
        "max_angular_velocity": _fixed(d, off + 48),
        "angular_recentering_velocity": _fixed(d, off + 52),
        "fast_angular_velocity": _fixed(d, off + 56),
        "fast_angular_maximum": _fixed(d, off + 60),
        "maximum_elevation": _fixed(d, off + 64),
        "external_angular_deceleration": _fixed(d, off + 68),
        "step_delta": _fixed(d, off + 72),
        "step_amplitude": _fixed(d, off + 76),
        "radius": _fixed(d, off + 80),
        "height": _fixed(d, off + 84),
        "dead_height": _fixed(d, off + 88),
        "camera_height": _fixed(d, off + 92),
        "splash_height": _fixed(d, off + 96),
        "half_camera_separation": _fixed(d, off + 100),
    }


# ---------------------------------------------------------------------------
# WPpx — weapon definitions (134 B = 62 main + 2 * 36 trigger)
# ---------------------------------------------------------------------------

WPPX_TRIGGER_RECORD = 36
WPPX_RECORD = 62 + 2 * WPPX_TRIGGER_RECORD


def _parse_trigger(d: bytes, off: int) -> dict:
    return {
        "rounds_per_magazine": _s16(d, off + 0),
        "ammunition_type": _s16(d, off + 2),
        "ticks_per_round": _s16(d, off + 4),
        "recovery_ticks": _s16(d, off + 6),
        "charging_ticks": _s16(d, off + 8),
        "recoil_magnitude": _wd(d, off + 10),
        "firing_sound": _s16(d, off + 12),
        "click_sound": _s16(d, off + 14),
        "charging_sound": _s16(d, off + 16),
        "shell_casing_sound": _s16(d, off + 18),
        "reloading_sound": _s16(d, off + 20),
        "charged_sound": _s16(d, off + 22),
        "projectile_type": _s16(d, off + 24),
        "theta_error": _s16(d, off + 26),
        "dx": _s16(d, off + 28),
        "dy": _s16(d, off + 30),
        "shell_casing_type": _s16(d, off + 32),
        "burst_count": _s16(d, off + 34),
    }


def parse_wppx_record(d: bytes, off: int) -> dict:
    main: dict[str, object] = {
        "item_type": _s16(d, off + 0),
        "powerup_type": _s16(d, off + 2),
        "weapon_class": _s16(d, off + 4),
        "flags": _u16(d, off + 6),
        "firing_light_intensity": _fixed(d, off + 8),
        "firing_light_intensity_decay_ticks": _s16(d, off + 12),
        "idle_height": _fixed(d, off + 14),
        "bob_amplitude": _fixed(d, off + 18),
        "kick_height": _fixed(d, off + 22),
        "reload_height": _fixed(d, off + 26),
        "idle_width": _fixed(d, off + 30),
        "horizontal_amplitude": _fixed(d, off + 34),
        "collection": _s16(d, off + 38),
        "idle_shape": _s16(d, off + 40),
        "firing_shape": _s16(d, off + 42),
        "reloading_shape": _s16(d, off + 44),
        # bytes 46-47: 2 B padding per Perl
        "charging_shape": _s16(d, off + 48),
        "charged_shape": _s16(d, off + 50),
        "ready_ticks": _s16(d, off + 52),
        "await_reload_ticks": _s16(d, off + 54),
        "loading_ticks": _s16(d, off + 56),
        "finish_loading_ticks": _s16(d, off + 58),
        "powerup_ticks": _s16(d, off + 60),
    }
    main["triggers"] = [
        _parse_trigger(d, off + 62 + 0 * WPPX_TRIGGER_RECORD),
        _parse_trigger(d, off + 62 + 1 * WPPX_TRIGGER_RECORD),
    ]
    return main


# ---------------------------------------------------------------------------
# Chunk-level dispatch
# ---------------------------------------------------------------------------

_CHUNK_DECODERS = {
    "MNpx": (parse_mnpx_record, MNPX_RECORD, "monsters"),
    "FXpx": (parse_fxpx_record, FXPX_RECORD, "effects"),
    "PRpx": (parse_prpx_record, PRPX_RECORD, "projectiles"),
    "PXpx": (parse_pxpx_record, PXPX_RECORD, "physics_constants"),
    "WPpx": (parse_wppx_record, WPPX_RECORD, "weapons"),
}


def decode_chunk(tag: str, data: bytes) -> list[dict] | None:
    """Decode one of the five physics chunks. Returns None if `tag` isn't recognized."""
    entry = _CHUNK_DECODERS.get(tag)
    if entry is None:
        return None
    parser, rec_size, _ = entry
    out = []
    for off in range(0, len(data) - (rec_size - 1), rec_size):
        try:
            out.append(parser(data, off))
        except Exception as e:
            out.append({"_error": str(e), "_offset": off})
    return out


def decode_embedded_physics(chunks: dict) -> dict:
    """Decode embedded physics chunks (e.g. from one Infinity level).

    `chunks` is a dict mapping 4-char tag (str or bytes) to chunk bytes.
    """
    out: dict = {}
    for tag, data in chunks.items():
        tag_name = tag if isinstance(tag, str) else tag.decode("mac-roman", errors="replace")
        records = decode_chunk(tag_name, data)
        if records is None:
            continue
        label = _CHUNK_DECODERS[tag_name][2]
        out[label] = records
    return out


# ---------------------------------------------------------------------------
# Marathon 1 record decoders
#
# M1 physics files use a different flat-chunk container (12 B per-chunk
# header: uint32 tag + 4 unused + uint16 count + uint16 size) and smaller
# record layouts. Many M2 fields aren't stored in the M1 format and the C++
# code synthesizes default values (FIXED_ONE pitch, NONE for missing sounds,
# etc.); we surface only what's actually in the bytes.
# ---------------------------------------------------------------------------

M1_MONS_RECORD = 138
M1_EFFE_RECORD = 6
M1_PROJ_RECORD = 36
M1_PHYS_RECORD = 100
M1_WEAP_RECORD = 120


def _parse_m1_damage(d: bytes, off: int) -> dict:
    """12-byte damage_definition shared by M1 monster and projectile records."""
    return {
        "type": _s16(d, off + 0),
        "flags": _u16(d, off + 2),
        "base": _s16(d, off + 4),
        "random": _s16(d, off + 6),
        "scale": _fixed(d, off + 8),
    }


def _parse_m1_attack(d: bytes, off: int) -> dict:
    """16-byte attack_definition used by M1 monsters."""
    return {
        "type": _s16(d, off + 0),
        "repetitions": _s16(d, off + 2),
        "error": _s16(d, off + 4),
        "range": _wd(d, off + 6),
        "shape": _shape_desc(_u16(d, off + 8)),
        "dx": _wd(d, off + 10),
        "dy": _wd(d, off + 12),
        "dz": _wd(d, off + 14),
    }


def parse_m1_mons_record(d: bytes, off: int) -> dict:
    return {
        "collection": _s16(d, off + 0),
        "vitality": _s16(d, off + 2),
        "immunities": _u32(d, off + 4),
        "weaknesses": _u32(d, off + 8),
        "flags": _u32(d, off + 12),
        "class": _u32(d, off + 16),
        "friends": _u32(d, off + 20),
        "enemies": _u32(d, off + 24),
        "activation_sound": _s16(d, off + 28),
        # bytes 30-31: conversation sound, ignored by Aleph One
        "flaming_sound": _s16(d, off + 32),
        "random_sound": _s16(d, off + 34),
        "random_sound_mask": _u16(d, off + 36),
        "carrying_item_type": _s16(d, off + 38),
        "radius": _wd(d, off + 40),
        "height": _wd(d, off + 42),
        "preferred_hover_height": _wd(d, off + 44),
        "minimum_ledge_delta": _wd(d, off + 46),
        "maximum_ledge_delta": _wd(d, off + 48),
        "external_velocity_scale": _fixed(d, off + 50),
        "impact_effect": _s16(d, off + 54),
        "melee_impact_effect": _s16(d, off + 56),
        "half_visual_arc": _s16(d, off + 58),
        "half_vertical_visual_arc": _s16(d, off + 60),
        "visual_range": _wd(d, off + 62),
        "dark_visual_range": _wd(d, off + 64),
        "intelligence": _s16(d, off + 66),
        "speed": _s16(d, off + 68),
        "gravity": _s16(d, off + 70),
        "terminal_velocity": _s16(d, off + 72),
        "door_retry_mask": _u16(d, off + 74),
        "shrapnel_radius": _s16(d, off + 76),
        "shrapnel_damage": _parse_m1_damage(d, off + 78),
        "hit_shape": _shape_desc(_u16(d, off + 90)),
        "hard_dying_shape": _shape_desc(_u16(d, off + 92)),
        "soft_dying_shape": _shape_desc(_u16(d, off + 94)),
        "hard_dead_shape": _shape_desc(_u16(d, off + 96)),
        "soft_dead_shape": _shape_desc(_u16(d, off + 98)),
        "stationary_shape": _shape_desc(_u16(d, off + 100)),
        "moving_shape": _shape_desc(_u16(d, off + 102)),
        "attack_frequency": _s16(d, off + 104),
        "melee_attack": _parse_m1_attack(d, off + 106),
        "ranged_attack": _parse_m1_attack(d, off + 122),
    }


def parse_m1_effe_record(d: bytes, off: int) -> dict:
    return {
        "collection": _s16(d, off + 0),
        "shape": _s16(d, off + 2),
        "flags": _u16(d, off + 4),
    }


def parse_m1_proj_record(d: bytes, off: int) -> dict:
    return {
        "collection": _s16(d, off + 0),
        "shape": _s16(d, off + 2),
        "detonation_effect": _s16(d, off + 4),
        "contrail_effect": _s16(d, off + 6),
        "ticks_between_contrails": _s16(d, off + 8),
        "maximum_contrails": _s16(d, off + 10),
        "radius": _wd(d, off + 12),
        "area_of_effect": _wd(d, off + 14),
        "damage": _parse_m1_damage(d, off + 16),
        "flags": _u16(d, off + 28),
        "speed": _wd(d, off + 30),
        "maximum_range": _wd(d, off + 32),
        "flyby_sound": _s16(d, off + 34),
    }


def parse_m1_phys_record(d: bytes, off: int) -> dict:
    """M1 player physics — same as M2 PXpx but lacks splash_height."""
    return {
        "max_forward_velocity": _fixed(d, off + 0),
        "max_backward_velocity": _fixed(d, off + 4),
        "max_perpendicular_velocity": _fixed(d, off + 8),
        "acceleration": _fixed(d, off + 12),
        "deceleration": _fixed(d, off + 16),
        "airborne_deceleration": _fixed(d, off + 20),
        "gravitational_acceleration": _fixed(d, off + 24),
        "climbing_acceleration": _fixed(d, off + 28),
        "terminal_velocity": _fixed(d, off + 32),
        "external_deceleration": _fixed(d, off + 36),
        "angular_acceleration": _fixed(d, off + 40),
        "angular_deceleration": _fixed(d, off + 44),
        "max_angular_velocity": _fixed(d, off + 48),
        "angular_recentering_velocity": _fixed(d, off + 52),
        "fast_angular_velocity": _fixed(d, off + 56),
        "fast_angular_maximum": _fixed(d, off + 60),
        "maximum_elevation": _fixed(d, off + 64),
        "external_angular_deceleration": _fixed(d, off + 68),
        "step_delta": _fixed(d, off + 72),
        "step_amplitude": _fixed(d, off + 76),
        "radius": _fixed(d, off + 80),
        "height": _fixed(d, off + 84),
        "dead_height": _fixed(d, off + 88),
        "camera_height": _fixed(d, off + 92),
        "half_camera_separation": _fixed(d, off + 96),
    }


def parse_m1_weap_record(d: bytes, off: int) -> dict:
    """M1 weapon definition — trigger fields are interleaved (T0/T1 pairs)
    rather than packed in separate sub-records like M2."""
    return {
        "item_type": _s16(d, off + 0),
        "weapon_class": _s16(d, off + 2),
        "flags": _u16(d, off + 4),
        "triggers": [
            {
                "ammunition_type": _s16(d, off + 6),
                "rounds_per_magazine": _s16(d, off + 8),
                "ticks_per_round": _s16(d, off + 58),
                "recovery_ticks": _s16(d, off + 66),
                "charging_ticks": _s16(d, off + 70),
                "recoil_magnitude": _wd(d, off + 74),
                "firing_sound": _s16(d, off + 78),
                "click_sound": _s16(d, off + 82),
                "reloading_sound": _s16(d, off + 86),
                "charging_sound": _s16(d, off + 88),
                "shell_casing_sound": _s16(d, off + 90),
                "sound_activation_range": _s16(d, off + 94),
                "projectile_type": _s16(d, off + 98),
                "theta_error": _s16(d, off + 102),
                "dx": _s16(d, off + 106),
                "dz": _s16(d, off + 108),
                "burst_count": _s16(d, off + 114),
            },
            {
                "ammunition_type": _s16(d, off + 10),
                "rounds_per_magazine": _s16(d, off + 12),
                "ticks_per_round": _s16(d, off + 60),
                "recovery_ticks": _s16(d, off + 68),
                "charging_ticks": _s16(d, off + 72),
                "recoil_magnitude": _wd(d, off + 76),
                "firing_sound": _s16(d, off + 80),
                "click_sound": _s16(d, off + 84),
                "shell_casing_sound": _s16(d, off + 92),
                "sound_activation_range": _s16(d, off + 96),
                "projectile_type": _s16(d, off + 100),
                "theta_error": _s16(d, off + 104),
                "dx": _s16(d, off + 110),
                "dz": _s16(d, off + 112),
                "burst_count": _s16(d, off + 116),
            },
        ],
        "firing_light_intensity": _fixed(d, off + 14),
        "firing_intensity_decay_ticks": _s16(d, off + 18),
        "idle_height": _fixed(d, off + 20),
        "bob_amplitude": _fixed(d, off + 24),
        "kick_height": _fixed(d, off + 28),
        "reload_height": _fixed(d, off + 32),
        "idle_width": _fixed(d, off + 36),
        "horizontal_amplitude": _fixed(d, off + 40),
        "collection": _s16(d, off + 44),
        "idle_shape": _s16(d, off + 46),
        "firing_shape": _s16(d, off + 48),
        "reloading_shape": _s16(d, off + 50),
        # bytes 52-53: unused
        "charging_shape": _s16(d, off + 54),
        "charged_shape": _s16(d, off + 56),
        "await_reload_ticks": _s16(d, off + 62),
        "ready_ticks": _s16(d, off + 64),
    }


_M1_CHUNK_DECODERS = {
    "mons": (parse_m1_mons_record, M1_MONS_RECORD, "monsters"),
    "effe": (parse_m1_effe_record, M1_EFFE_RECORD, "effects"),
    "proj": (parse_m1_proj_record, M1_PROJ_RECORD, "projectiles"),
    "phys": (parse_m1_phys_record, M1_PHYS_RECORD, "physics_constants"),
    "weap": (parse_m1_weap_record, M1_WEAP_RECORD, "weapons"),
}


def _looks_like_m1_physics(blob: bytes) -> bool:
    """Heuristic: M1 Physics.phys starts with one of the known 4-char chunk tags."""
    return len(blob) >= 12 and blob[:4].decode("mac-roman", errors="replace") in _M1_CHUNK_DECODERS


def _extract_m1_physics(blob: bytes) -> dict:
    """Walk an M1 Physics.phys file. Each chunk has a 12-byte header
    (uint32 tag + 4 padding + uint16 count + uint16 size) followed by
    count*size record bytes."""
    decoded: dict = {}
    pos = 0
    while pos + 12 <= len(blob):
        tag = blob[pos:pos + 4].decode("mac-roman", errors="replace")
        # bytes 4-7 unused
        count = _u16(blob, pos + 8)
        size = _u16(blob, pos + 10)
        payload = blob[pos + 12: pos + 12 + count * size]
        pos += 12 + count * size

        entry = _M1_CHUNK_DECODERS.get(tag)
        if entry is None:
            decoded[tag] = {"_raw_bytes": len(payload), "count": count, "size": size}
            continue
        parser, expected_size, label = entry
        if size != expected_size:
            # File's per-record size doesn't match what Aleph One expects.
            decoded[label] = {
                "_error": f"record size mismatch: file={size} expected={expected_size}",
                "count": count,
            }
            continue
        records = []
        for i in range(count):
            try:
                records.append(parser(payload, i * size))
            except Exception as e:
                records.append({"_error": str(e), "_offset": i * size})
        decoded[label] = records
    return decoded


# ---------------------------------------------------------------------------
# Top-level extractor
# ---------------------------------------------------------------------------

def extract(source_path: Path | str, dest_dir: Path | str) -> dict:
    """Extract a physics model file (M2/MI `Standard.phyA` or M1 `Physics.phys`).

    Output::

        <dest>/physics.json         -- structured dump of decoded chunks
        <dest>/manifest.json        -- counts + version info
        <dest>/Physics.raw          -- raw bytes (M1 fallback only)
    """
    blob = Path(source_path).read_bytes()
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    data, _rsrc, _meta = macbinary.unwrap(blob)
    payload = data if data is not None else blob

    decoded: dict = {}
    wad_info = None

    try:
        hdr = wad.read_header(payload)
    except Exception:
        hdr = None

    if hdr and hdr["version"] >= 1 and hdr["wad_count"] > 0:
        for entry in wad.read_directory(payload, hdr):
            if entry["length"] == 0:
                continue
            for tag, chunk_data in wad.read_chunks(payload, entry, hdr["entry_header_size"]):
                tag_name = wad.tag_str(tag)
                records = decode_chunk(tag_name, chunk_data)
                if records is None:
                    decoded[tag_name] = {
                        "_raw_bytes": len(chunk_data),
                        "_note": "no decoder registered for this tag",
                    }
                else:
                    label = _CHUNK_DECODERS[tag_name][2]
                    decoded[label] = records
        wad_info = {
            "version": hdr["version"], "name": hdr["name"],
            "wad_count": hdr["wad_count"],
        }
    elif _looks_like_m1_physics(payload):
        decoded = _extract_m1_physics(payload)
        wad_info = {"format": "m1-physics"}
    else:
        (dest_dir / "Physics.raw").write_bytes(blob)
        decoded["_note"] = (
            "Unrecognized physics file layout. Raw bytes preserved."
        )

    (dest_dir / "physics.json").write_text(
        json.dumps(decoded, indent=2), encoding="utf-8"
    )
    manifest = {
        "source": str(source_path),
        "wad_header": wad_info,
        "chunks": {k: len(v) for k, v in decoded.items() if isinstance(v, list)},
    }
    (dest_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest
