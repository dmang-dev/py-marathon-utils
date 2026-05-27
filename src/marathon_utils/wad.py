"""Aleph One / Bungie WAD container parser.

Handles both M1 (version 0) and M2/Infinity (version >= 1) WADs.
"""
import struct
from typing import Iterator, List, Tuple


def read_header(blob: bytes) -> dict:
    """Parse the 128-byte WAD header."""
    if len(blob) < 128:
        raise ValueError("blob too short for WAD header")
    version, data_version = struct.unpack(">hh", blob[0:4])
    name = blob[4:68].split(b"\x00", 1)[0].decode("mac-roman", errors="replace")
    checksum, dir_off, wad_count, app_sz, ent_sz_field, dir_sz_field = \
        struct.unpack(">IIhhhh", blob[68:84])
    parent_checksum = struct.unpack(">I", blob[84:88])[0]

    # M1 (version 0) ignores entry_header_size and dir_entry_base_size — substitute
    # the documented constants. M2+ honors the header fields plus app_specific size.
    if version < 1:
        entry_hdr_size, dir_entry_size = 12, 8
    else:
        entry_hdr_size = ent_sz_field if ent_sz_field else 16
        dir_entry_size = (dir_sz_field if dir_sz_field else 10) + app_sz

    return {
        "version": version,
        "data_version": data_version,
        "name": name,
        "checksum": checksum,
        "directory_offset": dir_off,
        "wad_count": wad_count,
        "app_specific_size": app_sz,
        "parent_checksum": parent_checksum,
        "entry_header_size": entry_hdr_size,
        "dir_entry_size": dir_entry_size,
    }


def read_directory(blob: bytes, hdr: dict) -> List[dict]:
    """Walk the WAD directory, returning one entry per level."""
    out = []
    de = hdr["dir_entry_size"]
    base = hdr["directory_offset"]
    for i in range(hdr["wad_count"]):
        rec = blob[base + i * de: base + i * de + de]
        if len(rec) < 8:
            break
        offset, length = struct.unpack(">II", rec[:8])
        name = None
        if de >= 84:  # M2 with embedded 64-byte level name
            name = rec[18:18 + 64].split(b"\x00", 1)[0].decode("mac-roman", "replace")
        out.append({"index": i, "offset": offset, "length": length, "name": name})
    return out


def read_chunks(blob: bytes, entry: dict, entry_hdr_size: int) -> Iterator[Tuple[bytes, bytes]]:
    """Yield (tag, data) for each chunk inside a level/wad-entry.

    Walks via next_offset (chunks may have trailing alignment padding so length
    alone isn't a safe stride).
    """
    base, total = entry["offset"], entry["length"]
    if total <= 0:
        return
    cur = 0
    seen = set()
    while cur < total:
        hdr = blob[base + cur: base + cur + entry_hdr_size]
        if len(hdr) < 12:
            return
        tag = hdr[0:4]
        next_off, length = struct.unpack(">ii", hdr[4:12])
        data_start = base + cur + entry_hdr_size
        data = blob[data_start: data_start + length]
        yield tag, data
        if next_off <= 0 or next_off in seen:
            return
        seen.add(next_off)
        cur = next_off


def tag_str(tag: bytes) -> str:
    """Decode a 4-byte chunk tag to a printable string."""
    return tag.decode("mac-roman", errors="replace").rstrip("\x00")
