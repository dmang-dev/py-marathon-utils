# Marathon Binary Format Reference

Byte-level layouts for the data files in all three Aleph One Marathon
releases (M1A1, Marathon 2, Marathon Infinity). All multi-byte fields are
**big-endian**. Strings are **MacRoman**. "Fixed" = signed 32-bit
fixed-point (divide by 65536 for float).

These notes were the basis for the Python parsers in this repo. If you're
implementing a Marathon reader in another language, start here.

### File extensions

| Game | Map | Shapes | Sounds | Wrapper |
|---|---|---|---|---|
| Marathon 1 | `Map.scen` | `Shapes.shps` | `Sounds.sndz` | MacBinary II |
| Marathon 2 | `Map.sceA` | `Shapes.shpA` | `Sounds.sndA` | M2 sounds: raw (`snd2`); M2 shapes: raw |
| Marathon Infinity | `Map.sceA` | `Shapes.shpA` | `Sounds.sndA` | (same as M2) |

Map files for all three versions ship MacBinary II-wrapped. Shapes and Sounds
are MacBinary II only on M1; M2/Infinity store them as raw container files.

## File-by-file detection

Three of the four M1 data files (`Map.scen`, `Shapes.shps`, `Sounds.sndz`) ship
as **MacBinary II** files. Strip the 128-byte envelope first. `Physics.phys` is
raw — no envelope.

MacBinary II detection heuristic (all must hold):

- `byte[0] == 0`
- `byte[74] == 0` (reserved)
- `byte[82] == 0` (reserved)
- `byte[1]` is in `[1..63]` (Pascal-style filename length)

## MacBinary II header (128 bytes)

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | old_version (=0) |
| 1 | 1 | filename_len |
| 2 | 63 | filename (MacRoman, null-padded) |
| 65 | 4 | file_type (`'scen'`, `'shps'`, `'sndz'`) |
| 69 | 4 | creator (`'26.2'` on Aleph One) |
| 73 | 1 | finder_flags_hi |
| 74 | 1 | reserved (=0) |
| 75 | 4 | window pos |
| 79 | 2 | folder ID |
| 81 | 1 | protected flag |
| 82 | 1 | reserved (=0) |
| 83 | 4 | data_fork_length (uint32 BE) |
| 87 | 4 | rsrc_fork_length (uint32 BE) |
| 91 | 4 | creation date (Mac epoch) |
| 95 | 4 | mod date |
| 99 | 2 | comment length |
| 101 | 1 | finder_flags_lo |
| 102–127 | 26 | MacBinary II extras + CRC |

File layout after the header:

```
[ 128 bytes MacBinary header ]
[ data_fork bytes, padded to multiple of 128 ]
[ rsrc_fork bytes, padded to multiple of 128 ]
```

## WAD container (Map.scen and Shapes.shps M2-style)

128-byte header followed by level data and a directory.

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | 2 | version | 0 = M1, ≥1 = M2/Infinity |
| 2 | 2 | data_version | |
| 4 | 64 | file_name | MacRoman, null-padded |
| 68 | 4 | checksum | |
| 72 | 4 | directory_offset | absolute |
| 76 | 2 | wad_count (level count) | |
| 78 | 2 | application_specific_directory_data_size | |
| 80 | 2 | entry_header_size | M1 ignores — use 12 |
| 82 | 2 | directory_entry_base_size | M1 ignores — use 8 |
| 84 | 4 | parent_checksum | |
| 88 | 40 | unused | |

### Directory entry

| M1 (8 B) | M2 (10 B + optional 74 B name) |
|---|---|
| `int32 offset; int32 length;` | `int32 offset; int32 length; int16 index;` + optional `int16 padding; char[64] name; int16 padding;` |

### Chunk header

| M1 (12 B) | M2 (16 B) |
|---|---|
| `char[4] tag; int32 next_offset; int32 length;` | same + trailing `int32 offset` |

Walk chunks by following `next_offset` (relative to the level's start). Stop when `next_offset == 0`.

## Map.scen chunks (M1)

### `EPNT` — endpoints (16 B each)

| Off | Type | Field |
|---|---|---|
| 0 | uint16 | flags |
| 2 | int16 | highest_adjacent_floor |
| 4 | int16 | lowest_adjacent_ceiling |
| 6 | int16 | x |
| 8 | int16 | y |
| 10 | int16 | transformed_x (runtime; ignore) |
| 12 | int16 | transformed_y |
| 14 | int16 | supporting_poly_index |

### `LINS` — lines (32 B each)

| Off | Type | Field |
|---|---|---|
| 0 | int16 | endpoint1 |
| 2 | int16 | endpoint2 |
| 4 | uint16 | flags |
| 6 | int16 | length |
| 8 | int16 | highest_adjacent_floor |
| 10 | int16 | lowest_adjacent_ceiling |
| 12 | int16 | cw_side_index |
| 14 | int16 | ccw_side_index |
| 16 | int16 | cw_poly_owner |
| 18 | int16 | ccw_poly_owner |
| 20 | 12 B | padding |

### `SIDS` — sides / wall textures (64 B each)

Key fields:

| Off | Type | Field |
|---|---|---|
| 0 | int16 | type |
| 2 | uint16 | flags |
| 4 | int16 | primary_tex_x |
| 6 | int16 | primary_tex_y |
| 8 | uint16 | primary_shape_descriptor |
| 10–20 | | secondary + transparent x,y,shape |
| 22 | 16 B | exclusion x,y (runtime) |
| 38 | int16 | panel_type |
| 40 | int16 | panel_permutation |
| 48 | int16 | poly_index |
| 50 | int16 | line_index |
| 58 | int32 | ambient_delta |

A `shape_descriptor` of `0xFFFF` means "no texture". Otherwise:
`shape = v & 0xff`, `collection = (v >> 8) & 0x1f`, `clut = (v >> 13) & 0x7`.

### `POLY` — polygons / sectors (128 B each)

Key fields for geometry:

| Off | Type | Field |
|---|---|---|
| 0 | int16 | type |
| 2 | uint16 | flags |
| 6 | uint16 | vertex_count (≤ 8) |
| 8 | int16[8] | endpoint_indices |
| 24 | int16[8] | line_indices |
| 40 | uint16 | floor_shape_descriptor |
| 42 | uint16 | ceiling_shape_descriptor |
| 44 | int16 | floor_height |
| 46 | int16 | ceiling_height |
| 48 | int16 | floor_light_index |
| 50 | int16 | ceiling_light_index |
| 56 | int16 | first_object |
| 68 | int16[8] | adjacent_polygon_indices |
| 92 | int16[8] | side_indices |
| 116 | int16 | media_index |
| 122 | int16 | ambient_sound_image_index |

### `LITE` — lights (M1: 32 B each)

| Off | Type | Field |
|---|---|---|
| 0 | uint16 | flags |
| 2 | int16 | type |
| 4 | int16 | mode |
| 6 | int16 | phase |
| 8 | Fixed | minimum_intensity |
| 12 | Fixed | maximum_intensity |
| 16 | int16 | period |
| 18 | Fixed | intensity |
| 22 | 10 B | padding |

### `LITE` — lights (M2 / Infinity: 100 B each)

Completely different layout. Six "function" blocks describe how the light
behaves in each state (active vs inactive; primary, secondary, transitions):

| Off | Type | Field |
|---|---|---|
| 0 | int16 | type |
| 2 | uint16 | flags |
| 4 | int16 | phase |
| 6 | 14 B | primary_active function block |
| 20 | 14 B | secondary_active function block |
| 34 | 14 B | becoming_active function block |
| 48 | 14 B | primary_inactive function block |
| 62 | 14 B | secondary_inactive function block |
| 76 | 14 B | becoming_inactive function block |
| 90 | int16 | tag |
| 92 | 8 B | padding |

Each 14-byte function block:

| Off | Type | Field |
|---|---|---|
| 0 | int16 | function |
| 2 | int16 | period |
| 4 | int16 | delta_period |
| 6 | Fixed | intensity |
| 10 | Fixed | delta_intensity |

### M2+ `medi`, `ambi`, `bonk`

- **`medi`** (32 B): liquids/media. `type, flags, light_index, current_direction,
  current_magnitude, low, high, origin_x, origin_y, height,
  min_light_intensity (Fixed), transparent_shape (uint16)`.
- **`ambi`** (16 B): ambient sound images. `flags, sound_index, volume`,
  + 10 B padding.
- **`bonk`** (32 B): random sound images. `flags, sound_index, volume,
  delta_volume, period, delta_period, direction, delta_direction,
  pitch (Fixed), delta_pitch (Fixed), phase`.

### M2+ `PLAT` — platforms (140 B each)

Replaces M1's smaller `plat` (32 B) chunk. Adds 8 `endpoint_owner` records
(8 B each) tracking which polygons/lines move with the platform.

### Infinity-only physics chunks

Marathon Infinity embeds **per-level physics models** so each level can
customize gameplay. The chunks are:

- `MNpx` — monster definitions
- `FXpx` — effect definitions
- `PRpx` — projectile definitions
- `PXpx` — physics constants
- `WPpx` — weapon definitions

py-marathon-utils preserves these as raw bytes for now (per-record decoding
is TBD — see `map2xml.pl` lines 572–812 for the field layouts).

### `OBJS` — object placements (16 B each)

| Off | Type | Field |
|---|---|---|
| 0 | int16 | type (monster/scenery/item/sound/etc.) |
| 2 | int16 | object_index within type |
| 4 | int16 | facing (512 = full circle) |
| 6 | int16 | polygon_index |
| 8 | int16 | location_x |
| 10 | int16 | location_y |
| 12 | int16 | location_z |
| 14 | uint16 | flags |

### `Minf` — static map info (88 B, single record)

| Off | Type | Field |
|---|---|---|
| 0 | int16 | environment_code |
| 2 | int16 | physics_model |
| 4 | int16 | song_index |
| 6 | int16 | mission_flags |
| 8 | int16 | environment_flags |
| 18 | char[66] | level_name |
| 84 | uint32 | entry_point_flags |

### `term` — terminal text (variable)

Per terminal:

```
uint16 total_length
uint16 flags         (bit 0 = text is XOR-encoded)
int16  lines_per_page
uint16 grouping_count
uint16 fontchange_count
[ grouping_count × 12 B ]
[ fontchange_count × 6 B ]
[ text bytes ]
```

De-obfuscation when `flags & 1`: for every 4-byte block, XOR byte 2 with `0xFE`
and byte 3 with `0xED`. Tail bytes (less than 4 left) XOR with `0xFE`.

## Coordinate conversion

Marathon stores positions/sizes as `int16` in units of `1/1024` World Unit.
World Unit ≈ 1 meter. To convert to (say) Unreal Engine centimeters:

```
ue_cm = (int16_value / 1024.0) * 100
```

A typical Marathon corridor (1 WU wide) is 100 UE cm.

## Shapes.shps / Shapes.shpA

Two completely different container layouts share the same per-collection
header structure.

### M1: lives in the rsrc fork

The MacBinary rsrc fork contains `.256` resources for collections (IDs
128–159, mapping to collections 0–31), plus `PICT` and `clut` resources used
by chapter screens and the system.

### M2/Infinity: flat 32-entry table

The file is NOT MacBinary-wrapped. It begins with a 32-entry collection-info
table (32 bytes per entry = 1024 bytes total):

| Off | Size | Field |
|---|---|---|
| 0 | 2 | status (int16) |
| 2 | 2 | flags (uint16) |
| 4 | 4 | off8 — offset to 8-bit collection (int32) |
| 8 | 4 | len8 — length of 8-bit collection |
| 12 | 4 | off16 — offset to 16-bit collection |
| 16 | 4 | len16 — length of 16-bit collection |
| 20 | 12 | padding |

After the table, the actual collection payloads live at `off8`/`off16`. Each
collection has the same 560-byte header described below, but the bitmap
encoding differs (M2 uses column-major sparse, not int16-opcode RLE).

### `.256` (collection) payload

Begins with a `uint32` total size, then a **560-byte collection header**:

| Off | Type | Field |
|---|---|---|
| 0 | int16 | version |
| 2 | int16 | type |
| 4 | uint16 | flags |
| 6 | int16 | color_count |
| 8 | int16 | clut_count |
| 10 | int32 | color_table_offset (rel. to collection start) |
| 14 | int16 | high_level_shape_count |
| 16 | int32 | high_level_shape_offset_table_offset |
| 20 | int16 | low_level_shape_count |
| 22 | int32 | low_level_shape_offset_table_offset |
| 26 | int16 | bitmap_count |
| 28 | int32 | bitmap_offset_table_offset |
| 32 | int16 | pixels_to_world |
| 34 | int32 | collection_size |
| 38 | 506 B | unused |

### CLUT entries (8 B each)

| Type | Field |
|---|---|
| uint8 | flags (0x80 = self-luminescent) |
| uint8 | value (palette slot this color occupies) |
| uint16 | red (0..65535) |
| uint16 | green |
| uint16 | blue |

The `value` field lets CLUTs be sparse — don't assume sequential order.

### Bitmap header

| Off | Type | Field |
|---|---|---|
| 0 | int16 | width |
| 2 | int16 | height |
| 4 | int16 | bytes_per_row (**-1 = M1 RLE**, ≥0 = raw) |
| 6 | uint16 | flags (0x8000 = column-order, 0x4000 = transparent) |
| 8 | int16 | bit_depth (= 8 in M1) |
| 10 | 16 B | reserved |
| 26 | 4×N | row/column address table |
| 26 + 4N | bytes | pixel data |

### M1 RLE format

For each row (or column, if `column-order`), a stream of `int16` opcodes:

- `opcode > 0`: read `opcode` literal bytes
- `opcode < 0`: skip `-opcode` bytes (already zero-filled)
- `opcode == 0`: end of line

### M2 / Infinity sparse format

Used when `bytes_per_row == -1`. Column-major: for each column (0..width-1):

```
int16 first_row
int16 last_row
bytes[last_row - first_row]  ← raw pixel indices for rows [first_row, last_row)
```

Rows outside `[first_row, last_row)` are transparent (or palette index 0).
- `opcode == 0`: end of line

Index 0 = transparent if the transparent flag is set.

### Effective view counts (high-level shapes)

The `number_of_views` field doesn't always equal the actual view count:

| `number_of_views` | Effective views |
|---|---|
| 10 | 1 (single static frame) |
| 3 | 4 |
| 9 or 11 | 5 |
| 5 | 8 |
| else | as-is |

## Sounds.sndz (M1)

Lives in the rsrc fork as `snd ` resources. M1 uses **only** format-1 stdSH —
uncompressed 8-bit unsigned mono PCM. No MACE/IMA decoder needed.

### `snd ` resource

```
uint16 format            (1 or 2)
If format == 1:
  uint16 num_modifiers
  For each modifier:  uint16 type, uint32 init_param  (6 B)
If format == 2:
  uint16 reference_count
uint16 num_sound_commands
For each command (8 B):
  uint16 cmd            (0x8050 = soundCmd, 0x8051 = bufferCmd, high bit = "dataOffset is buffer offset")
  uint16 param1
  uint32 param2         (offset of sound header for bufferCmd)
[ sound header at offset param2 ]
[ raw sample data follows ]
```

### Standard sound header (stdSH, 22 B + samples)

| Off | Type | Field |
|---|---|---|
| 0 | uint32 | sample_pointer (=0 in resource — data is inline) |
| 4 | uint32 | length (bytes of sample data) |
| 8 | Fixed | sample_rate (typical: `0x56EE8BA3` = 22254.5 Hz) |
| 12 | uint32 | loop_start |
| 16 | uint32 | loop_end |
| 20 | uint8 | encoding (0x00 = stdSH) |
| 21 | uint8 | base_frequency (60 = middle C) |
| 22 | bytes | sample data: `length` bytes of **unsigned 8-bit PCM** |

To convert to 16-bit signed WAV: `int16_sample = (uint8_byte - 128) * 256`.

## Sounds.sndA (M2 / Infinity)

Custom `snd2` container, not MacBinary. Header is 264 bytes total:

| Off | Size | Field |
|---|---|---|
| 0 | 4 | version (int32, 0 or 1) |
| 4 | 4 | tag (`'snd2'`) |
| 8 | 2 | source_count (int16) |
| 10 | 2 | sound_count (int16; if zero, treat source_count as sound_count and source_count=1) |
| 12 | 252 | unused / reserved |

Then `source_count * sound_count` sound metadata records (64 bytes each):

| Off | Size | Field |
|---|---|---|
| 0 | 2 | code (int16; -1 = empty slot) |
| 2 | 2 | behaviour_index (int16) |
| 4 | 2 | flags (uint16) |
| 6 | 2 | chance (uint16) |
| 8 | 4 | low_pitch (Fixed) |
| 12 | 2 | permutations_count (int16) |
| 14 | 2 | permutations_played (int16) |
| 16 | 4 | **group_offset** — absolute file offset of permutation data (int32) |
| 20 | 4 | single_length (int32) — bytes per permutation incl. header |
| 24 | 4 | total_length (int32) — sum across permutations |
| 28 | 20 | offsets[5] (int32 each) — distance from group_offset to each permutation |
| 48 | 4 | last_played (uint32) |
| 52 | 12 | private state / padding |

⚠️ The Common Lisp `aleph-one-sound-unpacker` assumes a slightly different
layout (a `high_pitch` Fixed at bytes 12–15) and treats `group_offset` as a
file-position relative to current — that layout doesn't match current Aleph
One M2A1/MI sndA files. We use the layout above, verified empirically by
tracing `group_offset` values to actual Mac sound header positions.

Permutation data at `group_offset + offsets[i]` is a classic Mac sound header
(see "Standard sound header" above). M2/Infinity may use stdSH (0x00), extSH
(0xFF, multi-channel/16-bit), or cmpSH "twos" (0xFE, signed 8-bit). The
encoding byte lives 20 bytes into the header.

The two sources are typically two quality levels (high-fi vs lo-fi) of the
same sound — extractors should output them in separate subdirectories.

## Physics.phys

No MacBinary wrapper. Roughly a flat dump of typed records using the M1 12-byte
entry header (`tag[4] next_offset[4] length[4]`), but in practice the
`next_offset` values in M1 physics files aren't reliable. Per-record decoding
of monster / weapon / projectile / effect fields is left as a TODO in this
library; see `marathon-utils/map2xml.pl` lines 572–812 for the field layouts.

## References

- [Aleph One source tree](https://github.com/Aleph-One-Marathon/alephone) —
  authoritative when format details disagree. Key files:
  `Source_Files/Files/wad.{h,cpp}`, `Source_Files/Sound/SoundFile.cpp`,
  `Source_Files/RenderMain/shape_descriptors.h`
- [marathon-utils](https://github.com/Hopper262/marathon-utils) — the Perl
  reference implementation
- [Marathon WAD format notes](https://gist.github.com/marrub--/98af41f36e15a277088b220a6a9f4244)
