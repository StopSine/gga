# GGA's file / overlay loader

Written for contributors working on the Goemon's Great Adventure recompilation.

Static recompilation cannot run an overlay system as-is: overlays are loaded to
runtime-chosen addresses and their absolute references are rewritten on load.
N64Recomp handles this by recompiling each overlay as its own section and
having the runtime apply relocations, which means the game's loader has to be
patched to call `recomp_load_overlays()` and `overlay_apply_relocations()`
instead of performing a raw DMA. The Mystical Ninja recompilation does this in
`patches/required.c`; this document identifies the equivalent site in GGA.

All addresses are USA (`NGME`), resident image, VRAM `0x80000400` = ROM
`0x1000` (`rom = vram - 0x7FFFF400`).

## The file table

The Nisitenma-Ichigo table lives at ROM `0x2C794`, i.e. VRAM `0x8002BB94`,
immediately after the 16-byte ASCII signature at ROM `0x2C784` / VRAM
`0x8002BB84`. Entries are 4 bytes, big-endian:

| bits | meaning |
|------|---------|
| 31   | compressed flag |
| 30-0 | ROM offset of the file |

A file's size is `entry[n+1] - entry[n]`, so entries are read in pairs. The
game addresses files with **1-based** ids: file `n` spans `entry[n-1]` to
`entry[n]`.

## Accessors

Two small helpers return masked offsets. Both discard bit 31, which is why
neither can be used to find the compression test:

| function | size | base | returns |
|----------|------|------|---------|
| `func_80004474_5074` | `0x2C` | `D_8002BB90` | `entry[i-1] & 0x7FFFFFFF` (start) |
| `func_8000449C_509C` | `0x2C` | `D_8002BB94` | `entry[i]   & 0x7FFFFFFF` (end)   |

`func_800042F0_4EF0` (`0x184`) calls them to turn a file id into a
`(rom_offset, size)` pair.

## The loader: `func_80003E50_4A50`

VRAM `0x80003E50`, size `0x1A0` (104 instructions). **This is the patch site.**

Unlike the accessors it reads the table *unmasked*, off the signature base, so
bit 31 survives:

- `D_8002BB84` + `(file_id - 1) * 4`, then loads `+0x10` and `+0x14` — the
  `0x10` skips the signature, giving `entry[file_id-1]` and `entry[file_id]`.
- `0x7FFFFFFF` is materialised separately to mask the offsets.
- `bgez` at `0x80003F04` tests the sign of the raw entry — this is the
  compressed-vs-raw decision.

Both paths, and the cache maintenance that follows:

| path | callee | size | role |
|------|--------|------|------|
| bit 31 set (fall-through) | `func_80002F40_3B40` | `0x594` (357 instrs) | decompressor |
| bit 31 clear (branch) | `func_80001CF8_28F8` | `0x40` (16 instrs) | raw DMA read |

After loading it calls `osWritebackDCache`, `osInvalDCache` and
`osInvalICache`. Those names were recovered by byte-matching against MNSG; see
`tools/match_libultra.py`.

Callers: `func_80003C94_4894`, `func_80003D2C_492C`, `func_80003E04_4A04`,
`func_80004250_4E50`.

This mirrors MNSG's patched loader, which tests
`D_800573D8_57FD8[cur_file_id] & FILE_COMP_MASK` and branches to a
decompressor or a raw read. GGA's loader does **not** byte-match MNSG's, so the
patch has to be written against GGA's own structure rather than adapted.

## Surrounding call chain

Traced upward from the table accessor:

```
func_8000449C_509C   0x2C    table lookup (end offset)
 <- func_800042F0_4EF0  0x184   id -> (rom_offset, size)
   <- func_800040D0_4CD0  0x180   osWritebackDCache
   <- func_80004250_4E50  0xA0    also calls the loader directly
     <- func_80003FF0_4BF0  0xE0
       <- func_80003B28_4728  0x16C
         <- func_80001294_1E94  0x15C   osRecvMesg - awaits completion
         <- func_8000397C_457C  0x110
```

`func_80010850_11450` (`0x580`) is the only function calling
`osEPiRawStartDma`, and has no direct callers, so it is reached indirectly —
consistent with a PI-manager thread rather than the loader's own path.

## What remains

Writing the patch needs these decompiled well enough to name the arguments:

1. `func_80003E50_4A50` — the loader itself: which register or stack slot holds
   the file id, the destination buffer and the size at the point where
   `recomp_load_overlays()` must be inserted.
2. `func_80002F40_3B40` — the decompressor, to confirm it consumes the chunk
   header's own codec bit (bit 31 selects zlib vs LZKN64 in GGA; see
   `tools/rommy.py`) rather than anything from the file table.
3. A mapping from file id to the recompiled section name (`.file_NN`), since
   `overlay_apply_relocations()` takes a section-relative id. The table ids and
   the segment names in `config/usa/gga.splat.yaml` already share numbering.

Note that only 40 of the 2577 files are relocatable overlays; the rest are raw
data or fixed-address code. See `tools/gen_overlay_segments.py`.

## The load-address table (`D_80026B00`)

A second table sits immediately before the Nisitenma-Ichigo signature, at VRAM
`0x80026B00` / ROM `0x27700`, running `8 * 2577 = 0x5088` bytes and ending at
ROM `0x2C788`, right where the signature begins. Each 8-byte record is a
`(vram_start, vram_end)` pair for the corresponding file, indexed by
`(file_id - 1) * 8`.

This is the authoritative answer to where every file loads, and it removes the
need to infer overlay addresses from `jal` targets:

| `vram_start` | meaning | files |
|--------------|---------|-------|
| `0x08000000` | relocatable overlay; relocated on load | 371 |
| real KSEG0   | fixed address, loaded to one specific window | 8 |

Of the 371 relocatable files, 47 contain code (`jr $ra` density); the rest are
data. `tools/gen_overlay_segments.py` currently finds 40 of those 47 by
heuristic, and every one of its 40 has `vram_start == 0x08000000` in this
table, so the heuristic was sound but incomplete.

The eight fixed-address files:

| file | window | size |
|------|--------|------|
| 1 | `0x800C7310..0x800C7B10` | `0x800` |
| 3 | `0x8036A000..0x8038F800` | `0x25800` |
| 4 | `0x8038F800..0x80400000` | `0x70800` |
| 5 | `0x800C7B10..0x801738A0` | `0xABD90` |
| 6 | `0x80342080..0x8036A000` | `0x27F80` |
| 7 | `0x801738A0..0x8017F0E0` | `0xB840` |
| 8 | `0x801738A0..0x801B7D50` | `0x444B0` |
| 9 | `0x801738A0..0x8019E810` | `0x2AF70` |

Files 7, 8 and 9 share the window at `0x801738A0`, so they are mutually
exclusive in RAM -- the same arrangement as MNSG, where 8 sections share
`0x801CB460`. They need `exclusive_ram_id` if they are ever split as segments.

Mapping file 5 would resolve four of the remaining stubs: the calls to
`func_800D05E0`, `func_800D3E64`, `func_800D3FF0` and `func_800D41AC` all land
inside `0x800C7B10..0x801738A0`.

`vram_end - vram_start` equals the decompressed size recorded in
`config/usa/rommy.yaml` for 1763 of 2577 files; the remainder are entries for
files that are never loaded, or whose window is a larger buffer than the file.

## Loader signature

`func_80003E50_4A50(u32 file_id, void *dest)`

- `$a0` — file id, 1-based. Rejected unless `0 < file_id < 0xA11` (2577, the
  exact file-table entry count); returns 0 when out of range.
- `$a1` — destination buffer, kept in `$s0` across the call.
- Table entries are read as `entry[file_id-1]` (start) and `entry[file_id]`
  (end) off the signature base, masked with `0x7FFFFFFF`, and the size is their
  difference. The compression flag is bit 31 of the file's *own* entry, which
  is re-loaded unmasked at `0x80003EF4` before the `bgez` test.
