#!/usr/bin/env python3
"""
Emit splat segments for Goemon's Great Adventure's loadable files.

Where the load addresses come from
----------------------------------
The engine carries a per-file load table at VRAM 0x80026B00 / ROM 0x27700,
immediately before the Nisitenma-Ichigo signature. Each 8-byte record is a
(vram_start, vram_end) pair indexed by the file's table index, so the game
itself states where every file is loaded. Two populations appear:

  * vram_start == 0x08000000 -- a relocatable overlay. The address is a
    placeholder; the loader relocates the file when it is loaded, which is the
    same convention MNSG uses. These need `overlay: yes` plus a shared
    `exclusive_ram_id`, since they all claim the same vram.
  * a real KSEG0 address -- the file is loaded to one specific window. Several
    files may share a window (7, 8 and 9 all load at 0x801738A0), which makes
    them mutually exclusive in RAM and so also an exclusive_ram_id group.

An earlier version of this script inferred overlays from `jal` targets landing
in 0x08xxxxxx. That heuristic agreed with the table on every file it found, but
only found 40 of the 47 code-bearing relocatable files, so the table is used
directly now.

Segment size is the file's own size from the Nisitenma-Ichigo table, not
vram_end - vram_start: the load window is frequently a larger buffer than the
file placed in it.

Code/data boundary
------------------
The last `jr $ra` plus its delay slot, rounded up so the split lands on a
multiple of the segment's subalign. Without that rounding the linker pads
between the two subsegments, every following section's load address drifts, and
N64Recomp reads instructions at the wrong ROM offset -- which surfaces as
"Unexpected reloc type 4" when a relocation lands on a non-jal.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

JR_RA = 0x03E00008
OVERLAY_BASE = 0x08000000
KSEG0_LO, KSEG0_HI = 0x80000000, 0x80800000
WORD = 4
SUBALIGN = 16


def read_file_table(rom: bytes, table_off: int) -> list[int]:
    offs = []
    e = table_off
    while True:
        w = struct.unpack_from(">I", rom, e)[0] & 0x7FFFFFFF
        if w == 0:
            break
        offs.append(w)
        e += WORD
    return offs


def load_window(rom: bytes, load_table: int, index: int) -> tuple[int, int]:
    return struct.unpack_from(">II", rom, load_table + 8 * index)


BRANCH_OPS = {0x01, 0x04, 0x05, 0x06, 0x07,
              0x14, 0x15, 0x16, 0x17}   # b* and their likely forms
JUMP_OPS = {0x02, 0x03}                 # j, jal


def code_extent(rom: bytes, start: int, end: int, vram: int,
                conservative: bool = False) -> tuple[int, int | None]:
    """
    Returns (jr_ra_count, code_end_rom aligned to SUBALIGN).

    The last `jr $ra` alone is not a safe boundary: a file can carry code after
    its final return (jump-table arms, tail blocks), and anything the code
    branches to that falls beyond the boundary ends up inside the data
    subsegment, where splat emits no label and the link fails with an undefined
    `.L` symbol. So the boundary is pushed out to the furthest control-flow
    target that still lands inside the file.

    Overshooting is worse than undershooting in the other direction, though:
    disassembling data as code can produce opcodes the assembler rejects for
    the vr4300 (`pref` is MIPS-IV), so the extent is never widened beyond the
    last instruction actually referenced.
    """
    jr = 0
    furthest = None
    for off in range(start, end, WORD):
        w = struct.unpack_from(">I", rom, off)[0]
        if w == JR_RA:
            jr += 1
            furthest = max(furthest or 0, off)
            continue
        op = w >> 26
        target = None
        if op in BRANCH_OPS:
            simm = w & 0xFFFF
            if simm & 0x8000:
                simm -= 0x10000
            target = off + WORD + simm * WORD
        elif op in JUMP_OPS:
            target = start + (((w & 0x03FFFFFF) << 2) - vram)
        if (not conservative) and target is not None and start <= target < end:
            furthest = max(furthest or 0, target)

    if furthest is None:
        return jr, None
    code_end = furthest + 2 * WORD
    code_end = start + ((code_end - start + SUBALIGN - 1) & ~(SUBALIGN - 1))
    return jr, min(code_end, end)


def main() -> int:
    ap = argparse.ArgumentParser(description="generate splat segments for GGA files")
    ap.add_argument("rom", type=Path)
    ap.add_argument("--table", type=lambda v: int(v, 0), default=0x2C794,
                    help="Nisitenma-Ichigo file table offset")
    ap.add_argument("--load-table", type=lambda v: int(v, 0), default=0x27700,
                    help="per-file (vram_start, vram_end) table offset")
    ap.add_argument("--start", type=lambda v: int(v, 0), default=0x26630)
    ap.add_argument("--end", type=lambda v: int(v, 0), default=0x2000000)
    ap.add_argument("--conservative", action="store_true",
                    help="end the code region at the last `jr $ra` instead of "
                         "the furthest control-flow target. Jump tables decode "
                         "as `j` instructions whose targets sit outside the "
                         "file, so extending to them sweeps table data into "
                         "the code region and produces bogus functions.")
    ap.add_argument("--relocatable-only", action="store_true",
                    help="skip files loaded to a fixed window. Those files "
                         "(5, 7, 8, 9) contain jump tables that the "
                         "control-flow boundary heuristic sweeps into the code "
                         "region, producing bogus functions whose `j` targets "
                         "land outside RDRAM; they need per-file jtbl analysis.")
    ap.add_argument("--no-data-split", action="store_true",
                    help="emit the whole file as asm instead of splitting off a "
                         "trailing data subsegment; the `jr $ra` boundary is "
                         "unreliable for files with code after the last one")
    ap.add_argument("--min-jr", type=int, default=20,
                    help="minimum `jr $ra` count for a file to count as code")
    args = ap.parse_args()

    rom = args.rom.read_bytes()
    offs = read_file_table(rom, args.table)

    segs = []  # (rom_start, rom_end, code_end, index, vram, ram_id)
    windows: dict[int, list[int]] = {}

    for i in range(len(offs) - 1):
        start, end = offs[i], offs[i + 1]
        if end <= start or end > len(rom) or start < args.start:
            continue

        vstart, vend = load_window(rom, args.load_table, i)
        if vend <= vstart:
            continue

        if vstart == OVERLAY_BASE:
            ram_id = "ovl"
        elif KSEG0_LO <= vstart < KSEG0_HI:
            if args.relocatable_only:
                continue
            ram_id = f"win_{vstart:08X}"
        else:
            continue  # not a RAM-loaded file

        jr, code_end = code_extent(rom, start, end, vstart, args.conservative)
        if jr < args.min_jr or code_end is None or code_end <= start:
            continue  # data-only; leave it in a bin segment

        segs.append((start, end, code_end, i, vstart, ram_id))
        windows.setdefault(vstart, []).append(i)

    segs.sort()

    out: list[str] = []
    cursor = args.start
    gap = 0
    for start, end, code_end, idx, vram, ram_id in segs:
        if start > cursor:
            out += [f"  - name: gap_{gap}", "    type: bin",
                    f"    start: 0x{cursor:X}", ""]
            gap += 1
        elif start < cursor:
            print(f"error: file {idx} at 0x{start:X} overlaps the previous segment",
                  file=sys.stderr)
            return 1

        kind = ("relocated on load" if vram == OVERLAY_BASE
                else f"loaded to a fixed window at 0x{vram:08X}")
        out += [
            f"  # File {idx}: {kind}.",
            f"  # Load window from the table at 0x{args.load_table:X}.",
            f"  - name: file_{idx}",
            "    type: code",
            f"    start: 0x{start:X}",
            f"    vram: 0x{vram:08X}",
            "    subalign: 16",
            "    overlay: yes",
            f"    exclusive_ram_id: {ram_id}",
            "    subsegments:",
            f"      - [0x{start:X}, asm, file_{idx}]",
        ]
        if code_end < end and not args.no_data_split:
            out.append(f"      - [0x{code_end:X}, data, file_{idx}_data]")
        out.append("")
        cursor = end

    if cursor < args.end:
        out += [f"  - name: gap_{gap}", "    type: bin", f"    start: 0x{cursor:X}", ""]
    out.append(f"  - [0x{args.end:X}]")

    print("\n".join(out))

    ovl = [s for s in segs if s[4] == OVERLAY_BASE]
    fixed = [s for s in segs if s[4] != OVERLAY_BASE]
    print(f"\n# {len(segs)} code segments: {len(ovl)} relocatable, {len(fixed)} fixed",
          file=sys.stderr)
    for start, end, code_end, idx, vram, ram_id in segs:
        print(f"#   file_{idx:<4} rom 0x{start:07X}..0x{end:07X} vram 0x{vram:08X} "
              f"code 0x{code_end - start:X} data 0x{end - code_end:X} [{ram_id}]",
              file=sys.stderr)
    shared = {v: ids for v, ids in windows.items() if len(ids) > 1 and v != OVERLAY_BASE}
    for v, ids in shared.items():
        print(f"# shared window 0x{v:08X}: files {ids} (mutually exclusive)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
