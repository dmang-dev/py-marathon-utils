"""py-marathon-utils — read Bungie Marathon / Aleph One data files in Python.

A pure-Python port of the byte-level parsing from
https://github.com/Hopper262/marathon-utils, focused on Marathon 1 (Aleph One
"M1A1" release) with extension points for Marathon 2 / Infinity.

Quick start::

    from marathon_utils import macbinary, wad, maps, sounds, shapes

    # Unwrap a MacBinary-encoded Aleph One file
    data, rsrc, meta = macbinary.unwrap_file("Map.scen")

    # Walk WAD header + directory
    header = wad.read_header(data)
    entries = wad.read_directory(data, header)

    # Or just call the high-level extractors
    maps.extract("Map.scen", "out/Maps")
    sounds.extract("Sounds.sndz", "out/Sounds")
    shapes.extract("Shapes.shps", "out/Shapes")    # PNGs (requires Pillow)

CLI::

    marathon-utils extract maps Map.scen out/Maps
    marathon-utils extract sounds Sounds.sndz out/Sounds
    marathon-utils extract shapes Shapes.shps out/Shapes
    marathon-utils visualize Map.scen out/PNG
"""

__version__ = "0.1.0"

from . import macbinary, macrsrc, maps, patches, physics, sounds, strings, wad

__all__ = [
           "__version__",
           "images",
           "macbinary",
           "macrsrc",
           "maps",
           "patches",
           "physics",
           "samsara",
           "shapes",
           "sounds",
           "strings",
           "terminals",
           "visualize",
           "wad",
]
# Note: `shapes`, `terminals`, `samsara`, `images`, and `visualize` need Pillow
# — they're not imported here so the package can load with stdlib only. Import
# them explicitly: `from marathon_utils import terminals`.
