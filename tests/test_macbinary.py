"""Unit tests for the MacBinary II unwrapper.

Uses crafted minimal inputs — no Marathon files required.
"""
from __future__ import annotations

import struct

from marathon_utils import macbinary


def _build_macbin(filename: bytes, file_type: bytes, data: bytes, rsrc: bytes) -> bytes:
    """Construct a minimal valid MacBinary II envelope."""
    hdr = bytearray(128)
    hdr[0] = 0
    hdr[1] = len(filename)
    hdr[2:2 + len(filename)] = filename
    hdr[65:69] = file_type
    hdr[69:73] = b"AONE"
    hdr[74] = 0
    hdr[82] = 0
    hdr[83:87] = struct.pack(">I", len(data))
    hdr[87:91] = struct.pack(">I", len(rsrc))
    # Pad data fork up to multiple of 128
    pad = (-len(data)) % 128
    return bytes(hdr) + data + b"\x00" * pad + rsrc


def test_unwrap_extracts_both_forks():
    blob = _build_macbin(b"test", b"scen", b"hello world", b"resource bytes")
    data, rsrc, meta = macbinary.unwrap(blob)
    assert data == b"hello world"
    assert rsrc == b"resource bytes"
    assert meta["filename"] == "test"
    assert meta["file_type"] == "scen"


def test_is_macbinary_rejects_nonzero_reserved():
    bad = bytearray(128)
    bad[0] = 0
    bad[1] = 4
    bad[2:6] = b"test"
    bad[74] = 1  # required-zero byte set
    assert not macbinary.is_macbinary(bytes(bad))


def test_is_macbinary_rejects_invalid_filename_length():
    bad = bytearray(128)
    bad[0] = 0
    bad[1] = 0  # zero-length name not allowed (range is 1..63)
    assert not macbinary.is_macbinary(bytes(bad))


def test_unwrap_returns_none_on_non_macbinary():
    data, rsrc, meta = macbinary.unwrap(b"not a macbinary file")
    assert data is None
    assert rsrc is None
    assert meta == {}


def test_unwrap_handles_empty_data_fork():
    blob = _build_macbin(b"icon", b"shps", b"", b"x" * 17)
    data, rsrc, _ = macbinary.unwrap(blob)
    assert data == b""
    assert rsrc == b"x" * 17
