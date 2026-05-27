"""Marathon 1 Sounds.sndz extractor.

The file is MacBinary-wrapped, with all sound resources in the rsrc fork as
classic Mac 'snd ' resources. M1 uses only stdSH (uncompressed 8-bit unsigned
PCM mono) so no MACE/IMA decoder is required.
"""
import struct
from pathlib import Path
from typing import Tuple

from . import macbinary, macrsrc

# Family naming hints — informational only; sound IDs aren't strictly grouped this
# way but the convention helps orient the output folder layout.
_FAMILY_PREFIXES = {
    1000: "monster",
    2000: "weapon",
    3000: "projectile",
    4000: "effect",
    5000: "ambient",
    6000: "platform",
    7000: "player",
    8000: "ui",
}


def family_for(sound_id: int) -> str:
    bucket = (sound_id // 1000) * 1000
    return _FAMILY_PREFIXES.get(bucket, "misc")


def parse_snd(data: bytes) -> Tuple[float, bytes]:
    """Parse one 'snd ' resource. Returns (sample_rate_hz, raw_pcm8u_bytes)."""
    fmt = struct.unpack(">H", data[0:2])[0]
    if fmt == 1:
        num_mods = struct.unpack(">H", data[2:4])[0]
        off = 4 + 6 * num_mods
    elif fmt == 2:
        off = 4
    else:
        raise ValueError(f"unknown snd format {fmt}")

    num_cmds = struct.unpack(">H", data[off: off + 2])[0]
    off += 2
    sound_off = None
    for i in range(num_cmds):
        cmd_off = off + i * 8
        cmd, _p1, p2 = struct.unpack(">HHI", data[cmd_off: cmd_off + 8])
        # Strip "dataOffset is buffer offset" bit (0x8000)
        if (cmd & 0x7FFF) in (0x0050, 0x0051):  # soundCmd / bufferCmd
            sound_off = p2
            break
    if sound_off is None:
        raise ValueError("no buffer/sound command found")

    # Standard sound header (22 B)
    _sample_ptr, length, rate_fx = struct.unpack(">III", data[sound_off: sound_off + 12])
    encoding = data[sound_off + 20]
    if encoding != 0x00:
        raise NotImplementedError(
            f"sound resource uses encoding 0x{encoding:02x} (stdSH only supported)"
        )
    rate_hz = rate_fx / 65536.0
    pcm = data[sound_off + 22: sound_off + 22 + length]
    return rate_hz, pcm


def write_wav(path: Path, rate_hz: float, pcm8u: bytes) -> None:
    """Write 16-bit PCM mono WAV. M1 stores 8-bit unsigned; we upconvert to 16-bit
    signed so the WAV is broadly compatible."""
    rate = max(1, round(rate_hz))
    sb = bytearray(2 * len(pcm8u))
    for i, b in enumerate(pcm8u):
        v = (b - 128) << 8
        sb[2 * i] = v & 0xFF
        sb[2 * i + 1] = (v >> 8) & 0xFF
    fmt_chunk = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    riff = (
        b"RIFF" + struct.pack("<I", 36 + len(sb)) + b"WAVEfmt "
        + struct.pack("<I", 16) + fmt_chunk
        + b"data" + struct.pack("<I", len(sb)) + bytes(sb)
    )
    path.write_bytes(riff)


def extract(source_path: Path, dest_dir: Path) -> dict:
    """Extract every 'snd ' resource from Sounds.sndz to dest_dir.

    Returns a manifest dict describing what was extracted.
    """
    blob = Path(source_path).read_bytes()
    _data, rsrc, _meta = macbinary.unwrap(blob)
    if rsrc is None:
        rsrc = blob  # No MacBinary wrapper — treat whole file as rsrc fork
    resources = macrsrc.parse(rsrc)
    snds = resources.get("snd ", [])

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"count": 0, "errors": [], "entries": []}
    for entry in snds:
        sid = entry["id"]
        family = family_for(sid)
        sub = dest_dir / family
        sub.mkdir(parents=True, exist_ok=True)
        try:
            rate_hz, pcm = parse_snd(entry["data"])
        except Exception as e:
            manifest["errors"].append({"id": sid, "error": str(e)})
            continue
        # Filename: 4-digit ID + name (if present) or just ID
        suffix = entry["name"] or ""
        safe_suffix = "".join(c if c.isalnum() or c in "-_ " else "_" for c in suffix).strip()
        fname = f"{sid:05d}" + (f"_{safe_suffix}" if safe_suffix else "") + ".wav"
        out_path = sub / fname
        write_wav(out_path, rate_hz, pcm)
        manifest["count"] += 1
        manifest["entries"].append({
            "id": sid,
            "name": entry["name"],
            "family": family,
            "rate_hz": round(rate_hz, 2),
            "samples": len(pcm),
            "duration_s": round(len(pcm) / rate_hz, 3),
            "path": str(out_path.relative_to(dest_dir)),
        })
    return manifest
