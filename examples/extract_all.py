"""Extract everything from a Marathon-20250829 scenario directory.

Usage:
    python examples/extract_all.py <path-to-Marathon-20250829> <out-dir>
"""
import sys
from pathlib import Path

from marathon_utils import maps, physics, shapes, sounds, visualize


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    dst.mkdir(parents=True, exist_ok=True)

    print(f"[maps]    {src / 'Map.scen'}")
    r = maps.extract(src / "Map.scen", dst / "Maps")
    print(f"          {r['level_count']} levels")

    print(f"[viz]     -> {dst / 'MapsViz'}")
    r = visualize.render_all_levels(src / "Map.scen", dst / "MapsViz")
    print(f"          {r['count']} PNGs")

    print(f"[sounds]  {src / 'Sounds.sndz'}")
    r = sounds.extract(src / "Sounds.sndz", dst / "Sounds")
    print(f"          {r['count']} WAVs")

    print(f"[shapes]  {src / 'Shapes.shps'}")
    r = shapes.extract(src / "Shapes.shps", dst / "Shapes")
    print(f"          {len(r['collections'])} collections, "
          f"{sum(c['bitmap_count'] for c in r['collections'])} bitmaps")

    print(f"[physics] {src / 'Physics.phys'}")
    r = physics.extract(src / "Physics.phys", dst / "Physics")
    print(f"          first chunk: {r['first_chunk_tag']!r}")

    print(f"\nDone. Output in {dst}")


if __name__ == "__main__":
    main()
