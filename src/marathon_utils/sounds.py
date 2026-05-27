"""Marathon sounds extractor (M1 .sndz + M2/Infinity .sndA).

M1 stores sounds as classic Mac 'snd ' resources in the MacBinary rsrc fork —
stdSH (uncompressed 8-bit unsigned mono PCM) only.

M2 and Infinity use a custom "snd2" container with per-sound permutations.
Permutations can use stdSH (8-bit unsigned), extSH (extended — multi-channel,
16-bit), or cmpSH (compressed "twos" = signed 8-bit, not actually compressed).
Other compression schemes (MACE 3:1/6:1, IMA4) exist in the spec but the
official Bungie M1A1/M2/MI files don't use them.
"""
from __future__ import annotations

import struct
from pathlib import Path

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

# Mac sound header encoding bytes (Inside Macintosh: Sound)
STDSH = 0x00
EXTSH = 0xFF
CMPSH = 0xFE

# Tag for the "twos" pseudo-compression scheme (just signed 8-bit PCM)
TWOS_TAG = 0x74776F73  # 'twos' big-endian uint32


# ---------------------------------------------------------------------------
# M1: classic Mac 'snd ' resource (stdSH only)
# ---------------------------------------------------------------------------

def parse_snd(data: bytes) -> tuple[float, bytes]:
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
        if (cmd & 0x7FFF) in (0x0050, 0x0051):  # soundCmd / bufferCmd
            sound_off = p2
            break
    if sound_off is None:
        raise ValueError("no buffer/sound command found")

    _sample_ptr, length, rate_fx = struct.unpack(">III", data[sound_off: sound_off + 12])
    encoding = data[sound_off + 20]
    if encoding != STDSH:
        raise NotImplementedError(
            f"snd resource uses encoding 0x{encoding:02x} (stdSH only supported)"
        )
    rate_hz = rate_fx / 65536.0
    pcm = data[sound_off + 22: sound_off + 22 + length]
    return rate_hz, pcm


# ---------------------------------------------------------------------------
# M2 / Infinity: snd2 container with per-permutation Mac sound headers
# ---------------------------------------------------------------------------

# Per Aleph One's source and the Common Lisp aleph-one-sound-unpacker, the
# snd2 outer header is 264 bytes total (16 fixed + 248 unused).
SND2_HEADER_BYTES = 264
# Per-sound metadata record size (before audio data, located in a block of
# `total_sound_count` consecutive records after the header).
SND2_SOUND_RECORD_BYTES = 64
_MAX_PERMUTATIONS = 5


def _read_snd2_header(blob: bytes) -> dict:
    if len(blob) < SND2_HEADER_BYTES:
        raise ValueError("file too short for snd2 header")
    version = struct.unpack(">i", blob[0:4])[0]
    tag = blob[4:8]
    if tag != b"snd2":
        raise ValueError(f"not an snd2 file: tag={tag!r}")
    if version not in (0, 1):
        raise ValueError(f"snd2 unsupported version {version}")
    source_count, sound_count = struct.unpack(">hh", blob[8:12])
    # When sound_count == 0, source_count actually carries the count (older layout).
    if sound_count == 0:
        sound_count = source_count
        source_count = 1
    return {
        "version": version,
        "source_count": source_count,
        "sound_count": sound_count,
        "total": source_count * sound_count,
    }


def _read_snd2_sound_record(blob: bytes, off: int) -> dict:
    """Parse one 64-byte snd2 sound metadata record.

    The layout we observed in the Aleph One M2/Infinity sndA files differs
    slightly from what the Common Lisp aleph-one-sound-unpacker assumes
    (which expected a high_pitch Fixed at bytes 12-15). The real layout, as
    verified by tracing record group_offset values to actual Mac sound
    header positions in the file, is:

        off  size  field
         0    2    code (int16)
         2    2    sound_behaviour (int16)
         4    2    flags (uint16)
         6    2    chance (uint16)
         8    4    low_pitch (int32 Fixed)
        12    2    permutations_count (int16)
        14    2    permutations_played (int16)
        16    4    group_offset (int32, absolute file offset)
        20    4    single_length (int32)
        24    4    total_length (int32)
        28   20    offsets[5] (int32)
        48    4    last_played (uint32)
        52   12    unused / private state

    group_offset is the absolute file offset of the first permutation's Mac
    sound header. Each offset[i] is added to group_offset to locate
    permutation i.
    """
    code, behaviour_index, flags, chance = struct.unpack(">hhHH", blob[off: off + 8])
    low_pitch = struct.unpack(">i", blob[off + 8: off + 12])[0]
    perm_count, perm_played = struct.unpack(">hh", blob[off + 12: off + 16])
    group_offset = struct.unpack(">i", blob[off + 16: off + 20])[0]
    single_length, total_length = struct.unpack(">ii", blob[off + 20: off + 28])
    offsets = list(struct.unpack(">5i", blob[off + 28: off + 48]))
    return {
        "code": code,
        "behaviour_index": behaviour_index,
        "flags": flags,
        "chance": chance,
        "low_pitch": low_pitch,
        "permutations_count": perm_count,
        "permutations_played": perm_played,
        "group_offset": group_offset,
        "single_length": single_length,
        "total_length": total_length,
        "offsets": offsets[:max(0, perm_count)],
    }


def _decode_permutation(blob: bytes, off: int) -> dict:
    """Decode one Mac sound resource header at `off`. Returns
    {sample_rate_hz, channels, sample_bits, signed, pcm_bytes}.

    Handles stdSH, extSH, and cmpSH ("twos" = signed-8-bit) encodings.
    Multi-channel / 16-bit samples are returned as their native bytes
    (caller's WAV writer handles them)."""
    if off + 21 > len(blob):
        raise ValueError("permutation header truncated")

    # Encoding byte lives 20 bytes into the header for both stdSH and ext/cmp.
    encoding = blob[off + 20]

    if encoding == STDSH:
        # stdSH: 4 unused, int32 length, uint32 rate(Fixed), 8 unused, byte encoding,
        # byte base_freq, then `length` bytes of unsigned 8-bit PCM.
        length = struct.unpack(">i", blob[off + 4: off + 8])[0]
        rate_fx = struct.unpack(">I", blob[off + 8: off + 12])[0]
        rate_hz = rate_fx / 65536.0
        pcm = blob[off + 22: off + 22 + length]
        return {
            "sample_rate_hz": rate_hz,
            "channels": 1,
            "sample_bits": 8,
            "signed": False,
            "pcm": pcm,
        }

    if encoding in (EXTSH, CMPSH):
        # Extended/compressed share the same first 22 bytes:
        # 4 unused, int32 channels, uint32 rate(Fixed), 8 unused (loopStart/End),
        # byte encoding, byte base_freq, int32 frame_count, ...
        channels = struct.unpack(">i", blob[off + 4: off + 8])[0]
        rate_fx = struct.unpack(">I", blob[off + 8: off + 12])[0]
        rate_hz = rate_fx / 65536.0
        frame_count = struct.unpack(">i", blob[off + 22: off + 26])[0]
        cur = off + 26  # after frame_count

        signed_eight = False
        if encoding == CMPSH:
            # Aleph One only knows the "twos" scheme (= signed 8-bit pcm).
            # Layout (continuing from cur): 14 B, uint32 compression_format,
            # 12 B, int16 compression_type, 4 B  →  total 36 more bytes.
            cur += 14
            comp_fmt = struct.unpack(">I", blob[cur: cur + 4])[0]
            cur += 4
            if comp_fmt != TWOS_TAG:
                raise NotImplementedError(
                    f"snd2 cmpSH compression {comp_fmt:#x} not supported"
                )
            cur += 12
            _comp_type = struct.unpack(">h", blob[cur: cur + 2])[0]
            cur += 2
            cur += 4
            signed_eight = True
        else:
            # extSH: skip 22 bytes of compression area before sample_bits
            cur += 22

        sample_bits = struct.unpack(">h", blob[cur: cur + 2])[0]
        cur += 2

        bytes_per_frame = (sample_bits // 8) * max(channels, 1)
        length = frame_count * bytes_per_frame
        pcm = blob[cur: cur + length]
        return {
            "sample_rate_hz": rate_hz,
            "channels": max(channels, 1),
            "sample_bits": sample_bits,
            "signed": signed_eight,
            "pcm": pcm,
        }

    raise NotImplementedError(f"unknown permutation encoding 0x{encoding:02x}")


# ---------------------------------------------------------------------------
# WAV writer (handles 8-bit unsigned, 8-bit signed→16, and 16-bit raw)
# ---------------------------------------------------------------------------

# Pre-computed translate tables — used by bytes.translate which runs at C speed
# and avoids per-byte Python loops (critical for M2 sounds where total sample
# count is in the millions per file).
_U8U_TO_S16_HIGH = bytes((b - 128) & 0xFF for b in range(256))   # unsigned → signed high byte
_U8S_TO_S16_HIGH = bytes(b for b in range(256))                  # signed twos-complement byte = high byte


def write_wav(path: Path, rate_hz: float, pcm: bytes, *,
              sample_bits: int = 8, channels: int = 1,
              signed_eight: bool = False,
              big_endian_sixteen: bool = True) -> None:
    """Write a PCM WAV.

    8-bit unsigned and 8-bit signed inputs are upconverted to 16-bit signed
    little-endian for broad compatibility. 16-bit samples that arrive as
    big-endian (the Marathon norm) are byte-swapped.
    """
    rate = max(1, round(rate_hz))

    if sample_bits == 8:
        # Build LE 16-bit by: low byte = 0 (already zero in bytearray),
        # high byte = signed reinterpretation of the 8-bit sample.
        table = _U8S_TO_S16_HIGH if signed_eight else _U8U_TO_S16_HIGH
        high = pcm.translate(table)
        sb = bytearray(2 * len(pcm))
        sb[1::2] = high
        out_pcm = bytes(sb)
        out_bits = 16
    elif sample_bits == 16:
        if big_endian_sixteen:
            # Byte-swap BE -> LE: swap each odd-indexed pair using slice assignment
            sb = bytearray(pcm)
            sb[0::2], sb[1::2] = bytes(pcm[1::2]), bytes(pcm[0::2])
            out_pcm = bytes(sb)
        else:
            out_pcm = pcm
        out_bits = 16
    else:
        raise NotImplementedError(f"unsupported sample_bits {sample_bits}")

    byte_rate = rate * channels * (out_bits // 8)
    block_align = channels * (out_bits // 8)
    fmt_chunk = struct.pack("<HHIIHH", 1, channels, rate, byte_rate, block_align, out_bits)
    riff = (
        b"RIFF" + struct.pack("<I", 36 + len(out_pcm)) + b"WAVEfmt "
        + struct.pack("<I", 16) + fmt_chunk
        + b"data" + struct.pack("<I", len(out_pcm)) + out_pcm
    )
    path.write_bytes(riff)


# ---------------------------------------------------------------------------
# Format detection + top-level extractor
# ---------------------------------------------------------------------------

def family_for(sound_id: int) -> str:
    bucket = (sound_id // 1000) * 1000
    return _FAMILY_PREFIXES.get(bucket, "misc")


def _is_snd2(blob: bytes) -> bool:
    """Detect M2/Infinity 'snd2' files (which are not MacBinary-wrapped)."""
    return len(blob) >= 8 and blob[4:8] == b"snd2"


def extract(source_path: Path | str, dest_dir: Path | str) -> dict:
    """Extract every sound from Sounds.sndz (M1) or Sounds.sndA (M2/Infinity).

    Detects format automatically. Returns a manifest of what was written.
    """
    blob = Path(source_path).read_bytes()
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if _is_snd2(blob):
        return _extract_snd2(blob, dest_dir)

    # Default: M1 MacBinary-wrapped Mac rsrc fork
    return _extract_m1(blob, dest_dir)


def _extract_m1(blob: bytes, dest_dir: Path) -> dict:
    _data, rsrc, _meta = macbinary.unwrap(blob)
    if rsrc is None:
        rsrc = blob
    resources = macrsrc.parse(rsrc)
    snds = resources.get("snd ", [])

    manifest: dict = {"format": "m1", "count": 0, "errors": [], "entries": []}
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
        suffix = entry["name"] or ""
        safe_suffix = "".join(c if c.isalnum() or c in "-_ " else "_" for c in suffix).strip()
        fname = f"{sid:05d}" + (f"_{safe_suffix}" if safe_suffix else "") + ".wav"
        out_path = sub / fname
        write_wav(out_path, rate_hz, pcm, sample_bits=8, channels=1)
        manifest["count"] += 1
        manifest["entries"].append({
            "id": sid,
            "name": entry["name"],
            "family": family,
            "rate_hz": round(rate_hz, 2),
            "samples": len(pcm),
            "duration_s": round(len(pcm) / rate_hz, 3) if rate_hz else None,
            "path": str(out_path.relative_to(dest_dir)),
        })
    return manifest


def _extract_snd2(blob: bytes, dest_dir: Path) -> dict:
    """Extract M2/Infinity snd2-format file.

    The file has `source_count` * `sound_count` records (typically 2 * 203).
    The two sources are usually low/high quality variants of the same sound,
    so we output as `s<source>/<NNNN>[_pN].wav`. The position within the
    `sound_count` block — not the `code` field, which is mostly 0 — identifies
    the in-game sound.
    """
    hdr = _read_snd2_header(blob)
    manifest: dict = {"format": "snd2", "header": hdr,
                      "count": 0, "errors": [], "entries": []}

    sound_table_off = SND2_HEADER_BYTES
    sound_count = hdr["sound_count"]
    for i in range(hdr["total"]):
        rec_off = sound_table_off + i * SND2_SOUND_RECORD_BYTES
        if rec_off + SND2_SOUND_RECORD_BYTES > len(blob):
            break
        try:
            rec = _read_snd2_sound_record(blob, rec_off)
        except Exception as e:
            manifest["errors"].append({"index": i, "error": f"record: {e}"})
            continue
        if rec["code"] == -1 or rec["permutations_count"] <= 0:
            continue  # empty slot

        source_idx = i // sound_count if sound_count > 0 else 0
        sound_idx = i % sound_count if sound_count > 0 else i
        sub = dest_dir / f"s{source_idx}"
        sub.mkdir(parents=True, exist_ok=True)

        for pi, perm_off in enumerate(rec["offsets"]):
            # group_offset is an absolute file offset; offsets[i] is the
            # distance from group_offset to permutation i's Mac sound header.
            absolute_off = rec["group_offset"] + perm_off
            try:
                perm = _decode_permutation(blob, absolute_off)
            except Exception as e:
                manifest["errors"].append({
                    "index": i, "permutation": pi,
                    "offset": absolute_off, "error": str(e),
                })
                continue

            tag = "" if rec["permutations_count"] == 1 else f"_p{pi}"
            fname = f"{sound_idx:04d}{tag}.wav"
            out_path = sub / fname
            try:
                write_wav(
                    out_path,
                    perm["sample_rate_hz"],
                    perm["pcm"],
                    sample_bits=perm["sample_bits"],
                    channels=perm["channels"],
                    signed_eight=perm["signed"],
                )
            except Exception as e:
                manifest["errors"].append({
                    "index": i, "permutation": pi, "error": f"wav write: {e}",
                })
                continue

            manifest["count"] += 1
            manifest["entries"].append({
                "source": source_idx,
                "sound_index": sound_idx,
                "code": rec["code"],
                "permutation": pi,
                "rate_hz": round(perm["sample_rate_hz"], 2),
                "channels": perm["channels"],
                "sample_bits": perm["sample_bits"],
                "bytes": len(perm["pcm"]),
                "path": str(out_path.relative_to(dest_dir)),
            })
    return manifest
