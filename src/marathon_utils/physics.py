"""Physics.phys extractor.

Unlike the other M1 data files, Physics.phys is raw (no MacBinary wrapper)
and stores a small set of typed chunks back-to-back using the M1 12-byte
entry header. We emit a JSON listing of the chunks present; full per-record
decoding of monster/weapon/projectile stats is deferred until needed by the
gameplay pass.
"""
import json
from pathlib import Path


def extract(source_path: Path, dest_dir: Path) -> dict:
    """Preserve the raw Physics.phys plus a chunk-table best-effort dump.

    M1 physics uses an old layout where next_offset values are unreliable;
    full per-record decoding of monster/weapon/projectile fields lives in a
    later TODO. For now we keep the binary accessible and record the file's
    first chunk tag (typically 'mons') for orientation.
    """
    blob = Path(source_path).read_bytes()
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    (dest_dir / "Physics.phys.raw").write_bytes(blob)
    first_tag = blob[0:4].decode("mac-roman", errors="replace").rstrip("\x00") if len(blob) >= 4 else ""

    manifest = {
        "source": str(source_path),
        "file_size": len(blob),
        "first_chunk_tag": first_tag,
        "notes": (
            "M1 Physics.phys does not use the standard WAD chunk framing; per-record decoding "
            "(monster/weapon/projectile fields) is deferred to the gameplay/AI implementation pass."
        ),
        "chunks": [{"tag": first_tag, "offset": 0, "length": len(blob)}] if first_tag else [],
    }
    (dest_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
