# py-marathon-utils

Read Bungie Marathon / Aleph One data files (maps, sprites, sounds) in pure Python.

A clean-room Python port of the byte-level parsing in
[Hopper262/marathon-utils](https://github.com/Hopper262/marathon-utils), plus
some extension for formats that upstream doesn't cover. Supports all three
Marathon games shipped by Aleph One:

| Game | Map | Shapes | Sounds | Levels |
|---|---|---|---|---|
| **Marathon 1** (M1A1) | ✅ | ✅ | ✅ | 37 |
| **Marathon 2: Durandal** | ✅ | ✅ | ✅ | 41 |
| **Marathon Infinity** | ✅ | ✅ | ✅ | 57 |

Useful if you're modding, porting Marathon to a different engine, building a
level previewer, or just poking at the data files for fun.

Map parsing for M1 is cross-validated against the reference Perl
implementation: **bit-exact** on all 7,595 polygons across 37 levels
(see [tests/test_perl_parity.py](tests/test_perl_parity.py)).

## Install

```bash
pip install py-marathon-utils                  # core (stdlib only)
pip install "py-marathon-utils[images]"        # adds shape PNG + map viz (Pillow)
pip install "py-marathon-utils[dev]"           # dev: pytest, ruff, mypy
```

Python 3.8+.

## Quick start

### CLI

```bash
# Marathon 1
marathon-utils extract maps    Map.scen    out/Maps      # per-level JSON
marathon-utils extract sounds  Sounds.sndz out/Sounds    # WAV files
marathon-utils extract shapes  Shapes.shps out/Shapes    # sprite/texture PNGs
marathon-utils visualize       Map.scen    out/PNG       # top-down level images

# Marathon 2 / Infinity (same commands, different file extensions)
marathon-utils extract maps    Map.sceA    out/Maps
marathon-utils extract sounds  Sounds.sndA out/Sounds
marathon-utils extract shapes  Shapes.shpA out/Shapes
marathon-utils visualize       Map.sceA    out/PNG
```

Format auto-detection means you don't need to tell the CLI which Marathon
version a file is from — it figures it out from the bytes.

### Library

```python
from marathon_utils import macbinary, wad, maps, sounds

# Unwrap MacBinary II
data, rsrc, meta = macbinary.unwrap_file("Map.scen")

# Walk the WAD
header = wad.read_header(data)
print(f"M1 WAD v{header['version']}: {header['wad_count']} levels named {header['name']!r}")

for entry in wad.read_directory(data, header):
    for tag, payload in wad.read_chunks(data, entry, header['entry_header_size']):
        print(entry['index'], wad.tag_str(tag), len(payload))

# High-level extractors
result = maps.extract("Map.scen", "out/Maps")
for lev in result['levels'][:3]:
    print(f"{lev['index']:>2} {lev['name']!r}  "
          f"polygons={lev['polygon_count']} lights={len(lev.get('LITE') or [])}")
```

## What it can do

| File (M1 / M2-MI) | Reader | Output | Status |
|---|---|---|---|
| `Map.scen` / `Map.sceA` | `marathon_utils.maps` | per-level JSON (geometry, lights, objects, terminal text) | ✅ M1 + M2 + Infinity |
| `Sounds.sndz` / `Sounds.sndA` | `marathon_utils.sounds` | 16-bit WAV files | ✅ M1 (Mac rsrc) + M2/Infinity (snd2) |
| `Shapes.shps` / `Shapes.shpA` | `marathon_utils.shapes` | per-collection palette + per-shape PNG | ✅ M1 (RLE) + M2/Infinity (sparse) |
| `Physics.phys` | `marathon_utils.physics` | raw passthrough + manifest | 🟡 Stub (no per-record decode) |
| any WAD | `marathon_utils.wad` | walk chunks programmatically | ✅ M1 v0 + M2 v2 + Infinity v4 |
| MacBinary II | `marathon_utils.macbinary` | unwrap to data+rsrc forks | ✅ |
| Mac OS resource fork | `marathon_utils.macrsrc` | typed `{resource_type: [{id, name, data}, ...]}` | ✅ |

Plus a top-down map visualizer (`marathon_utils.visualize`) that renders each
level as a PNG suitable for level-design review.

### Version-specific notes

- **M1 maps** use 32-byte LITE records and use the `plat` (lowercase) chunk
  for platforms.
- **M2 / Infinity maps** use 100-byte LITE records with six function blocks
  (primary/secondary/becoming-active and -inactive states), use the `PLAT`
  (uppercase) chunk format, and add `medi` / `ambi` / `bonk` chunks for media,
  ambient sound images, and random sound images. Directory entries embed the
  64-byte level name (no need to read the `NAME` chunk).
- **Infinity** adds **per-level embedded physics chunks** (`MNpx`, `FXpx`,
  `PRpx`, `PXpx`, `WPpx`) that let each level customize monster/projectile/
  weapon/physics constants. They're preserved as raw bytes in the JSON for now.
- **Shape files**: M1 stores collections as `.256` Mac resources with row/
  column int16-opcode RLE bitmaps; M2+ uses a flat 32-entry collection table
  with column-major sparse `(first_row, last_row, pixels)` bitmaps.
- **Sound files**: M1 uses classic Mac `snd ` resources; M2/Infinity use a
  custom `snd2` container with per-sound permutations. Both support stdSH
  (8-bit unsigned), extSH (multi-channel/16-bit), and cmpSH "twos" (signed
  8-bit) headers.

## What it doesn't do (yet)

These exist in the upstream Perl marathon-utils but aren't ported. PRs welcome:

- Anvil-format patch files (`patch2xml.pl`, `xml2patch.pl`, `applypatch.pl`)
- Resource → MML conversion (`rsrc2mml.pl`)
- Marathon 2 Preview Shapes (`prevshapes2xml.pl`) — historical/niche
- Per-record decoding of `Physics.phys` (M1) and the embedded physics chunks
  (Infinity) — both currently preserve raw bytes
- 16-bit shape banks (M2/Infinity ships an 8-bit and 16-bit version of each
  collection; we render the 8-bit bank, which carries the canonical sprites)
- `Images.imgA` (M2/Infinity chapter screens and title art) — separate format
- The Marathon: Durandal XBLA assets (`cma2wavs.pl`, `cmt2dds.pl`, `live2dir.pl`,
  `mark2dir.pl`) — separate codebase, separate game
- Reverse direction (write back to binary) — read-only for v0.1

## Format reference

Byte-level layouts for all supported formats are documented in
[`docs/format-reference.md`](docs/format-reference.md). If you're writing a
parser in another language, that doc is the easiest read.

## Cross-validation

`tests/test_perl_parity.py` runs the upstream `map2xml.pl` (if Perl is on PATH)
and compares its XML output to ours. Currently bit-exact for all M1 maps.

```bash
pytest tests/test_perl_parity.py -v
```

## License

[MIT](LICENSE). Use it for whatever — modding, ports, ROM-archaeology, your
side project.

## Acknowledgements

- **[Hopper262](https://github.com/Hopper262/marathon-utils)** — the Perl
  scripts whose byte-layout decoders this port is based on. These are the
  reference implementation; this library is a clean-room idiomatic Python
  translation of the format knowledge.
- **[Aleph One](https://github.com/Aleph-One-Marathon/alephone)** — the open
  source Marathon engine, source of truth for any format ambiguity.
- **[Bungie](https://www.bungie.net/)** for making Marathon and later
  releasing the source.

## Disclaimer

This is a third-party tool. Marathon and its assets are property of Bungie.
Aleph One's free distribution license for the game data does not transfer
to derivative projects; if you extract assets with this library, treat them
as Bungie IP for redistribution purposes.
