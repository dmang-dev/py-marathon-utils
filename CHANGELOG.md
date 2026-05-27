# Changelog

All notable changes to py-marathon-utils. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
