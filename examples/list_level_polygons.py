"""Library-mode example: list polygon counts and floor/ceiling extremes per level.

Usage:
    python examples/list_level_polygons.py <Map.scen>
"""
import sys
from pathlib import Path

from marathon_utils import macbinary, maps, wad


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    src = Path(sys.argv[1])

    data, _r, _m = macbinary.unwrap(src.read_bytes())
    if data is None:
        data = src.read_bytes()
    hdr = wad.read_header(data)
    directory = wad.read_directory(data, hdr)

    print(f"{'idx':>3} {'name':<46} {'polys':>5} {'floor':>7} {'ceiling':>7}")
    print("-" * 75)
    for entry in directory:
        if entry["length"] == 0:
            continue
        level = maps.parse_level(data, entry, hdr)
        name = level["data"].get("Minf", {}).get("level_name", f"Level_{entry['index']}")
        poly = level["data"].get("POLY", [])
        if not poly:
            continue
        fh = min(p["floor_height"] for p in poly)
        ch = max(p["ceiling_height"] for p in poly)
        print(f"{entry['index']:>3} {name:<46} {len(poly):>5} {fh:>7} {ch:>7}")


if __name__ == "__main__":
    main()
