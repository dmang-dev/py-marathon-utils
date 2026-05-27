"""Classic Mac OS resource fork parser.

Used by Shapes.shps and Sounds.sndz which carry their payload in the rsrc fork
of their MacBinary wrapper.

Resource fork layout (all big-endian):
  Header (16 B): dataOffset, mapOffset, dataSize, mapSize
  Data block at dataOffset: per-resource length-prefixed payloads
  Map block at mapOffset:   header copy + type list + name list
"""
import struct
from typing import Dict, List


def parse(rsrc: bytes) -> Dict[str, List[dict]]:
    """Return {'snd ': [{'id': int, 'name': str|None, 'data': bytes}, ...], ...}."""
    if len(rsrc) < 16:
        return {}
    data_offset, map_offset, _data_size, _map_size = struct.unpack(">IIII", rsrc[0:16])
    if map_offset + 30 > len(rsrc):
        return {}

    # Resource map: 16 B header copy + 4 next-handle + 2 fileref + 2 attrs +
    #               2 type_list_offset + 2 name_list_offset
    type_list_offset = struct.unpack(">H", rsrc[map_offset + 24: map_offset + 26])[0]
    name_list_offset = struct.unpack(">H", rsrc[map_offset + 26: map_offset + 28])[0]
    tl_abs = map_offset + type_list_offset
    nl_abs = map_offset + name_list_offset

    num_types_minus_1 = struct.unpack(">H", rsrc[tl_abs: tl_abs + 2])[0]
    num_types = (num_types_minus_1 + 1) & 0xFFFF
    if num_types_minus_1 == 0xFFFF:
        num_types = 0

    result: Dict[str, List[dict]] = {}
    # Each type record is 8 B: 4 type code + 2 numRefs-1 + 2 ref_list_offset (from type list start)
    for ti in range(num_types):
        rec_off = tl_abs + 2 + ti * 8
        type_code = rsrc[rec_off: rec_off + 4].decode("mac-roman", errors="replace")
        num_refs_minus_1, ref_list_rel = struct.unpack(">HH", rsrc[rec_off + 4: rec_off + 8])
        num_refs = num_refs_minus_1 + 1
        ref_list_abs = tl_abs + ref_list_rel

        entries = []
        for ri in range(num_refs):
            r_off = ref_list_abs + ri * 12
            rid, name_off = struct.unpack(">hh", rsrc[r_off: r_off + 4])
            attrs_data = struct.unpack(">I", rsrc[r_off + 4: r_off + 8])[0]
            # attrs in high byte, data_offset in low 24 bits (relative to dataOffset)
            data_rel = attrs_data & 0x00FFFFFF
            data_abs = data_offset + data_rel
            payload_len = struct.unpack(">I", rsrc[data_abs: data_abs + 4])[0]
            payload = rsrc[data_abs + 4: data_abs + 4 + payload_len]

            name = None
            if name_off != -1 and nl_abs + name_off < len(rsrc):
                nlen = rsrc[nl_abs + name_off]
                name = rsrc[nl_abs + name_off + 1: nl_abs + name_off + 1 + nlen].decode(
                    "mac-roman", errors="replace"
                )

            entries.append({"id": rid, "name": name, "data": payload})
        result[type_code] = entries

    return result
