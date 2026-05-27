"""MacBinary II unwrapper.

Marathon's Aleph One ships its data files (Map.scen, Shapes.shps, Sounds.sndz,
Marathon.appl) wrapped in MacBinary II. We need the inner data/rsrc forks.
"""
import struct
from pathlib import Path
from typing import Optional, Tuple


def is_macbinary(blob: bytes) -> bool:
    """Sanity heuristic for MacBinary II per the spec's required-zero bytes."""
    if len(blob) < 128:
        return False
    if blob[0] != 0 or blob[74] != 0 or blob[82] != 0:
        return False
    return 1 <= blob[1] <= 63


def unwrap(blob: bytes) -> Tuple[Optional[bytes], Optional[bytes], dict]:
    """Return (data_fork, rsrc_fork, meta). Forks may be empty bytes; both None if not MacBinary."""
    if not is_macbinary(blob):
        return None, None, {}
    filename = blob[2:2 + blob[1]].decode("mac-roman", errors="replace")
    file_type = blob[65:69].decode("mac-roman", errors="replace")
    creator = blob[69:73].decode("mac-roman", errors="replace")
    data_len = struct.unpack(">I", blob[83:87])[0]
    rsrc_len = struct.unpack(">I", blob[87:91])[0]
    data_pad = (data_len + 127) & ~127  # round up to multiple of 128
    data = blob[128:128 + data_len]
    rsrc_start = 128 + data_pad
    rsrc = blob[rsrc_start:rsrc_start + rsrc_len]
    meta = {
        "filename": filename,
        "file_type": file_type,
        "creator": creator,
        "data_len": data_len,
        "rsrc_len": rsrc_len,
    }
    return data, rsrc, meta


def unwrap_file(path: Path) -> Tuple[Optional[bytes], Optional[bytes], dict]:
    return unwrap(Path(path).read_bytes())
