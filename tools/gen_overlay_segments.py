#!/usr/bin/env python3
"""
Emit splat segments for Goemon's Great Adventure's relocatable overlays.

Identifying them
----------------
MIPS `jal` encodes target = (PC & 0xF0000000) | (imm26 << 2), so the linked
address is baked into the instruction stream with only its top nibble dropped.
GGA's overlays are linked at the 0x08000000 placeholder base and relocated when
loaded -- the same convention the Mystical Ninja recompilation uses, where 57
of 72 sections sit at vram 0x08000000. A file whose jal targets land in
0x08xxxxxx is therefore a relocatable overlay, and its vram is 0x08000000
rather than any real address.

Code/data boundary
------------------
Taken as the last `jr $ra` plus its delay slot. Everything after that is
emitted as a data subsegment, which matters because the code references it
(splat names those symbols D_08xxxxxx) and the link fails with undefined
references if the data stays inside a bin segment.

Output
------
A YAML segment list covering the ROM from --start to the end, with bin
segments filling the gaps between overlays. Splice it into the splat config
after the resident `main` segment.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

JR_RA = 0x03E00008
JAL_OP = 3
OVERLAY_BASE = 0x08000000
OVERLAY_LIMIT = 0x09000000
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


def classify(rom: bytes, start: int, end: int) -> tuple[bool, int | None]:
    """
    Returns (is_relocatable_overlay, code_end_rom).

    code_end_rom is the last `jr $ra` plus delay slot, or None if no code.
    """
    jr_count = 0
    last_jr = None
    overlay_targets = 0
    other_targets = 0

    for off in range(start, end, WORD):
        w = struct.unpack_from(">I", rom, off)[0]
        if w == JR_RA:
            jr_count += 1
            last_jr = off
        if (w >> 26) == JAL_OP:
            target = (w & 0x03FFFFFF) << 2
            if OVERLAY_BASE <= target < OVERLAY_LIMIT:
                overlay_targets += 1
            else:
                other_targets += 1

    is_overlay = (
        jr_count >= 20
        and overlay_targets > 0
        and overlay_targets >= other_targets
    )
    if last_jr is None:
        return is_overlay, None

    # Round the code/data split up so its offset within the segment is a
    # multiple of the segment's subalign (16). Otherwise the linker pads
    # between the two subsegments, the output section grows, and every
    # following section's load address drifts. N64Recomp then derives a ROM
    # address that is off by the accumulated padding, reads the wrong
    # instructions, and dies on a relocation that lands on a non-jal
    # ("Unexpected reloc type 4").
    code_end = last_jr + 2 * WORD
    code_end = start + ((code_end - start + SUBALIGN - 1) & ~(SUBALIGN - 1))
    if code_end > end:
        code_end = end
    return is_overlay, code_end


def main() -> int:
    ap = argparse.ArgumentParser(description="generate splat segments for GGA overlays")
    ap.add_argument("rom", type=Path, help="decompressed ROM")
    ap.add_argument("--table", type=lambda v: int(v, 0), default=0x2C794,
                    help="Nisitenma-Ichigo file table offset")
    ap.add_argument("--start", type=lambda v: int(v, 0), default=0x26630,
                    help="first ROM offset this segment list covers")
    ap.add_argument("--end", type=lambda v: int(v, 0), default=0x2000000,
                    help="end of ROM (final segment marker)")
    ap.add_argument("--min-size", type=lambda v: int(v, 0), default=0x400)
    ap.add_argument("--ram-id", default="ovl",
                    help="exclusive_ram_id shared by all overlays")
    args = ap.parse_args()

    rom = args.rom.read_bytes()
    offs = read_file_table(rom, args.table)

    overlays = []
    for i in range(len(offs) - 1):
        start, end = offs[i], offs[i + 1]
        if end <= start or end > len(rom) or (end - start) < args.min_size:
            continue
        if start < args.start:
            continue
        is_overlay, code_end = classify(rom, start, end)
        if is_overlay and code_end is not None and code_end > start:
            overlays.append((i, start, end, code_end))

    overlays.sort(key=lambda o: o[1])

    out: list[str] = []
    cursor = args.start
    gap = 0

    for idx, start, end, code_end in overlays:
        if start > cursor:
            out.append(f"  - name: gap_{gap}")
            out.append("    type: bin")
            out.append(f"    start: 0x{cursor:X}")
            out.append("")
            gap += 1
        elif start < cursor:
            print(f"error: file {idx} at 0x{start:X} overlaps previous segment "
                  f"(cursor 0x{cursor:X})", file=sys.stderr)
            return 1

        out.append(f"  # File {idx} of the Nisitenma-Ichigo table. Linked at the")
        out.append(f"  # 0x08000000 placeholder base and relocated on load.")
        out.append(f"  - name: file_{idx}")
        out.append("    type: code")
        out.append(f"    start: 0x{start:X}")
        out.append(f"    vram: 0x{OVERLAY_BASE:08X}")
        out.append("    subalign: 16")
        # Every overlay claims the same vram, so splat must be told they are
        # mutually exclusive in RAM. Without this it resolves a reference that
        # escapes one segment into whichever other segment covers that vram.
        out.append("    overlay: yes")
        out.append(f"    exclusive_ram_id: {args.ram_id}")
        out.append("    subsegments:")
        out.append(f"      - [0x{start:X}, asm, file_{idx}]")
        if code_end < end:
            out.append(f"      - [0x{code_end:X}, data, file_{idx}_data]")
        out.append("")
        cursor = end

    if cursor < args.end:
        out.append(f"  - name: gap_{gap}")
        out.append("    type: bin")
        out.append(f"    start: 0x{cursor:X}")
        out.append("")

    out.append(f"  - [0x{args.end:X}]")

    print("\n".join(out))
    print(f"\n# {len(overlays)} relocatable overlays", file=sys.stderr)
    for idx, start, end, code_end in overlays:
        print(f"#   file_{idx:<4} rom 0x{start:07X}..0x{end:07X} "
              f"code 0x{code_end - start:X} data 0x{end - code_end:X}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
