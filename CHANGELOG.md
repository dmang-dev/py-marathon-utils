# Changelog

All notable changes to py-marathon-utils. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Packaging & quality

- **Self-contained terminal fonts.** The renderer's bitmap fonts are now
  generated from the SIL-OFL **Courier Prime** font (`scripts/generate_fonts.py`)
  and bundled inside the package (`marathon_utils/fonts/`), matching the classic
  Courier12 metrics. Terminal rendering works from an installed wheel with no
  external font files. Removed the dependency on the (unbundled) marathon-utils
  font files.
- **Wheel/sdist build**: `python -m build` produces a clean wheel that bundles
  the fonts + `py.typed`; verified by installing into a fresh venv and rendering
  a terminal. Passes `twine check`.
- **PEP 561**: added `py.typed` so downstream type-checkers consume our hints.
- **Single-source version**: `__version__` in `marathon_utils/__init__.py` is
  now the one source of truth (pyproject reads it dynamically).
- **mypy clean** across all 16 modules; **ruff** clean. CI now runs ruff + mypy,
  a 3.8/3.10/3.12 test matrix, and a build-and-verify-wheel job. Added a
  `.pre-commit-config.yaml`.
- Removed the vendored `vendor/marathon-utils/` (unlicensed upstream; the parity
  test now uses a local clone via `MARATHON_UTILS_DIR` and skips otherwise).
- Pillow floor raised to >=9.1 (uses the `Image.Transpose` / `Image.Resampling`
  enums).

### Added — Images.imgA chapter art (QuickDraw PICT v2 decoder)

- `images`: new module decodes the M2/Infinity `Images.imgA` chapter screens
  and title art to PNG. Not part of upstream marathon-utils (Hopper handles
  PICTs in a separate `classic-mac-utils` repo) — this is a from-scratch
  QuickDraw PICT v2 decoder. Handles the opcodes Marathon uses:
  `PackBitsRect` (8-bit indexed + embedded ColorTable), and `DirectBitsRect`
  in both 16-bit RGB555 (packType 3, PackBits on 16-bit units) and 32-bit
  planar RGB (packType 4, cmpCount 3). Includes a reusable PackBits codec.
  Decodes all 14 M2 + 17 Infinity PICTs with zero errors (verified against
  the Marathon 2: Durandal title screen across all three pixel formats).
- CLI: new `marathon-utils extract images <Images.imgA> <out>` subcommand.
- 6 new tests (PackBits codec units + full M2/MI decode).

### Added — 16-bit shape banks

- `shapes.parse_m2_collections(include_16bit=True)`: each populated M2/Infinity
  collection slot now yields its 16-bit bank in addition to the 8-bit bank
  (tagged `bit_depth`). In M2 five collections ship a 16-bit bank (interface +
  chapter/scenery art at 256-color depth); Infinity likewise. Pass
  `include_16bit=False` for the previous 8-bit-only behavior.
- `shapes.write_m2`: writes both banks back to their `off8/len8` and
  `off16/len16` table slots, contiguous in slot order (8-bit before 16-bit) to
  match the original layout. Round-trips pixel-perfect across all 1,341 (M2) /
  1,565 (Infinity) bitmaps spanning both banks.
- `shapes.extract`: renders the 16-bit bank to a `Coll_<NN>_16bit/` sibling
  directory alongside the 8-bit `Coll_<NN>/`.

### Added — Shapes writer, M1 terminals, marine composer, terminal tooling

- `shapes.write_m2` + `shapes.parse_m2_collections`: round-trip writer for
  M2 / Infinity `.shpA` files. Port of `xml2shapes.pl`. Rebuilds the 32-entry
  collection table, 544-byte collection headers, and the ctab / hlsh / llsh /
  bmap sections with their embedded offset tables. Validated pixel-perfect on
  all 1,288 bitmaps across 29 M2 collections (parse → write → re-parse yields
  visually identical bitmaps; column-major raw bitmaps are normalized to
  row-major storage, which changes byte order but not the rendered image).
- `terminals.compile_m1_script`: compiles Marathon 1's human-readable terminal
  scripts (`;L000.WELCOME.ENTRY`, `#logon`, `#information`, `$B…$b` inline
  styling) into the same grouping/font-change structure the renderer consumes.
  `terminals.extract` now auto-detects M1 `Marathon.appl` and renders its
  terminals too — the iconic "Arrival" Leela broadcast renders end-to-end.
- `terminals.terminal_locations`: port of `termxml2locations.pl`. Finds
  `computer_terminal` control panels in a parsed level and returns their world
  coordinates (M1 and M2/Infinity panel-type tables).
- `terminals.generate_html_preview`: port of `html_preview.pl`. Emits a
  browsable `index.html` grouping rendered terminal PNGs by level.
- `samsara`: port of `shapesxml2marine.pl` (the Samsara Doom-mod helper).
  Composites Marathon's layered marine player sprites (collection 6) — legs +
  torso anchored via key points — into per-color/torso/leg/view PNGs.
  Abbreviated mode (~7,680 sprites) or `--full-animation` (~23k frames).
- CLI: new `marathon-utils marines <Shapes> <out>` command; `extract terminals`
  now accepts `Marathon.appl` as well as map files.
- Tests: writer round-trip (2) + terminal helpers/compiler/Samsara (8).

### Added — Terminal renderer, writers, and resource MML

- `terminals`: full port of `termxml2images.pl` (835 lines of Perl). Renders
  Marathon 2 / Infinity terminal screens as PNG pages with the iconic
  green-on-black classic look. Includes a bitmap font loader (parses the
  Courier12/Bold/Italic .txt format), style-run extraction from M2's
  `font_change` records, monospace greedy text wrapping, and the per-status
  page-counter naming scheme (`<level>_s<term>[u|s|f]_p<page>.png`).
  Verified rendering Durandal's iconic "Welcome back" opening from Marathon
  2's level 0 with the word "Marathon" properly italicized.
- `maps.parse_terminal`: now decodes the full `groupings` and `font_changes`
  arrays (previously only counted them and emitted text). This is the input
  format the new renderer consumes.
- `patches.write`: round-trip writer for Anvil patches. Validated bit-perfect
  on the real CTF Flag Shapes Patch from Simplici7y.
- `strings`: extended to also parse `clut` (interface colors), `nrct`
  (interface rectangles), and `finf` (font info) resources from
  `Marathon.appl`. `to_mml()` now emits the corresponding `<interface>`
  block plus `<color>/<rect>/<font>` override elements — full feature parity
  with `rsrc2mml.pl`.
- CLI: new `marathon-utils extract terminals <Map.sceA> <out>` subcommand.
- 14 new tests (7 terminals + 3 writers + 4 strings).

### Added — M1 physics + Anvil patches

- `physics`: M1 `Physics.phys` now fully decoded. M1 uses an older flat-chunk
  container (12 B per-chunk header: `uint32 tag + 4 padding + uint16 count
  + uint16 size`) with five smaller records: `mons` (138 B), `effe` (6 B),
  `proj` (36 B), `phys` (100 B), `weap` (120 B). Layout extracted from
  Aleph One's `unpack_m1_*_definition` functions. Field names are aligned
  to the M2 equivalents where they match.
- `patches`: new module reads Anvil-format shape patches (community texture/
  sprite override packs distributed via Simplici7y et al.). Port of
  `patch2xml.pl`. Includes a working `apply()` that overlays a patch onto a
  parsed shapes result — the upstream `applypatch.pl` only stubbed this with
  a `# tbd` comment, so this is functionality beyond the Perl reference.
  Validated against a real community patch (CTF Flag Shapes Patch from
  Simplici7y) — see `scripts/fetch_sample_patches.py`.
- CLI: new `marathon-utils extract patches <patch-file> <out>` subcommand.
- 8 more tests (4 patches + updated M1 physics).

### Added — Strings and full physics decoding

- `strings`: new module ports `strings2xml.pl`. Reads `STR `, `STR#`, `TEXT`,
  and Marathon 1's `term` (human-readable terminal script) resources from any
  Mac resource fork. Optional `to_mml()` helper emits Aleph One MML
  `<stringset>` blocks. Big use case: pulling the per-level terminal lore
  out of `Marathon.appl` that the M1 level WADs don't carry.
- `physics`: full per-record decoders for MNpx (monsters, 156 B), FXpx
  (effects, 14 B), PRpx (projectiles, 48 B), PXpx (player physics constants,
  104 B), and WPpx (weapons, 134 B = 62 main + 2 × 36 triggers). Works on
  M2/Infinity `Standard.phyA` and on Infinity's per-level embedded chunks
  via `decode_embedded_physics()`.
- `maps`: per-level `embedded_physics` dict now appears in Infinity level
  JSON, decoded via the new physics module. Other Marathon versions are
  unaffected.
- CLI: new `marathon-utils extract strings <Marathon.appl> <out>` subcommand.
- 17 new tests in `test_strings.py` + `test_physics.py`.

### Added — Marathon 2 / Infinity support

- `maps`: version-aware chunk parsing. M2/Infinity LITE records (100 B, six
  function blocks) and the `medi`/`ambi`/`bonk` chunks now decode correctly.
  Added an M2-format `PLAT` parser alongside the M1 `plat` parser. M1
  behavior is unchanged — original Perl-parity tests still pass.
- `shapes`: auto-detects M1 (Mac resource fork, row/column int16-opcode RLE)
  vs M2/Infinity (flat collection-info table, column-major sparse bitmaps).
  Both render to per-collection PNG.
- `sounds`: added M2/Infinity `snd2` container support with the corrected
  per-record layout (group_offset is absolute, perm_count is at byte 12 not
  16 — the upstream Common Lisp reference had this wrong for current files).
  Vectorized 8-bit-to-16-bit WAV conversion using `bytes.translate` (300×
  faster on M2/Infinity sample volumes).
- `visualize`: works on M1/M2/Infinity maps with no API changes (consumes
  parsed levels directly).
- WAD parser correctly handles M1 v0, M2 v2, and Infinity v4 headers.
- 11 new integration tests covering all three Marathon versions
  (`tests/test_m2_mi.py`).



## [0.1.0] — 2026-05-27

Initial release. Clean-room Python port of the relevant subset of
[Hopper262/marathon-utils](https://github.com/Hopper262/marathon-utils),
focused on Marathon 1 (Aleph One M1A1 release).

### Added

- `macbinary` — MacBinary II unwrapper
- `wad` — Bungie WAD container parser (M1 v0 + M2 / Infinity)
- `macrsrc` — Classic Mac OS resource fork parser
- `maps` — `Map.scen` → per-level JSON (geometry, lights, object placements,
  de-obfuscated terminal text)
- `sounds` — `Sounds.sndz` → 16-bit mono WAV, organized by family
- `shapes` — `Shapes.shps` (M1) → per-collection palette + per-shape PNG.
  Includes the M1 RLE bitmap decoder. Requires Pillow.
- `physics` — raw `Physics.phys` passthrough + manifest stub
- `visualize` — top-down map renderer using Pillow ImageDraw
- CLI: `marathon-utils extract <kind> <src> <dst>` and `visualize`
- Test suite including Perl-parity cross-check against the upstream
  marathon-utils reference (`pytest tests/test_perl_parity.py`)

### Known limitations

- Marathon 2 / Infinity shape files not yet supported (M1 only)
- Per-record decoding of `Physics.phys` not implemented
- Anvil-format patch files (mod-distribution format) not supported
- Read-only: no writers for any format yet
