# Changelog

All notable changes to py-marathon-utils. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
