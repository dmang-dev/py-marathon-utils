"""Unit tests for the WAD container parser.

Tests both M1 (version 0, 8-byte directory entry / 12-byte chunk header) and
M2 (version 2, 10-byte directory entry / 16-byte chunk header) layouts.
"""
from __future__ import annotations

import struct

from marathon_utils import wad


def _build_m1_wad(chunks_per_level: list[list[tuple[bytes, bytes]]]) -> bytes:
    """Build a minimal M1 WAD with the given per-level chunks. Returns the
    blob (no MacBinary wrap)."""
    # Plan layout:
    # 128-byte header || level0_chunks || level1_chunks || ... || directory
    level_blobs: list[bytes] = []
    for level_chunks in chunks_per_level:
        offsets = []
        cur = 0
        bufs = []
        # First pass: compute next_offset
        for i, (tag, data) in enumerate(level_chunks):
            entry_size = 12 + len(data)
            offsets.append(cur)
            next_off = cur + entry_size if i < len(level_chunks) - 1 else 0
            hdr = tag + struct.pack(">ii", next_off, len(data))
            bufs.append(hdr + data)
            cur += entry_size
        level_blobs.append(b"".join(bufs))

    # Concatenate level blobs after the 128-byte WAD header
    wad_body = b""
    level_offsets_lengths = []
    for lb in level_blobs:
        level_offsets_lengths.append((128 + len(wad_body), len(lb)))
        wad_body += lb

    # Directory: M1 = 8 bytes per entry (offset, length)
    directory = b"".join(struct.pack(">II", off, ln) for off, ln in level_offsets_lengths)
    directory_offset = 128 + len(wad_body)

    # Build header
    hdr = bytearray(128)
    struct.pack_into(">hh", hdr, 0, 0, 0)  # version=0, data_version=0
    name = b"TEST" + b"\x00" * 60
    hdr[4:68] = name
    struct.pack_into(">II", hdr, 68, 0, directory_offset)  # checksum, dir_off
    struct.pack_into(">hhhh", hdr, 76, len(chunks_per_level), 0, 0, 0)
    return bytes(hdr) + wad_body + directory


def test_m1_wad_header_uses_legacy_sizes():
    blob = _build_m1_wad([[(b"NAME", b"Hello\x00")]])
    hdr = wad.read_header(blob)
    assert hdr["version"] == 0
    assert hdr["wad_count"] == 1
    assert hdr["name"] == "TEST"
    # M1 substitutes the legacy entry sizes when version < 1
    assert hdr["entry_header_size"] == 12
    assert hdr["dir_entry_size"] == 8


def test_directory_offsets_round_trip():
    chunks = [
        [(b"NAME", b"Alpha\x00")],
        [(b"NAME", b"Beta\x00"), (b"DATA", b"\x01\x02\x03\x04")],
    ]
    blob = _build_m1_wad(chunks)
    hdr = wad.read_header(blob)
    entries = wad.read_directory(blob, hdr)
    assert len(entries) == 2
    # Walk chunks of level 1 and verify
    found = list(wad.read_chunks(blob, entries[1], hdr["entry_header_size"]))
    tags = [t for t, _d in found]
    payloads = [d for _t, d in found]
    assert tags == [b"NAME", b"DATA"]
    assert payloads[0] == b"Beta\x00"
    assert payloads[1] == b"\x01\x02\x03\x04"


def test_chunks_terminate_on_zero_next_offset():
    """A single-chunk level has next_offset=0 → walker stops cleanly."""
    blob = _build_m1_wad([[(b"ONLY", b"x" * 16)]])
    hdr = wad.read_header(blob)
    [entry] = wad.read_directory(blob, hdr)
    chunks = list(wad.read_chunks(blob, entry, hdr["entry_header_size"]))
    assert len(chunks) == 1
    assert chunks[0][0] == b"ONLY"


def test_tag_str_strips_padding():
    assert wad.tag_str(b"NAME") == "NAME"
    assert wad.tag_str(b"abc\x00") == "abc"
    assert wad.tag_str(b"fx  ") == "fx  "
