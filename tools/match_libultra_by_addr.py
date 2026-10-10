#!/usr/bin/env python3
"""Match GGA's anonymous libultra functions against MNSG's named ones.

Unlike lib/gga/tools/match_libultra.py this does not need a syms.toml for the
reference: MNSG's symbol_addrs.txt gives only name -> address, so instead of
comparing whole functions we take each GGA function's size and compare that
many bytes at each MNSG address. Identical routines match exactly.

Instruction words are compared with address-bearing fields masked out, since
the same routine linked elsewhere differs only there. Register fields are kept,
which is what keeps the near-identical device-busy primitives distinguishable.
"""

import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

WORD = 4

# opcodes whose 16-bit immediate is address-bearing
IMM_OPS = {
    0x08, 0x09, 0x0C, 0x0D, 0x0E, 0x0F,          # addi/addiu/andi/ori/xori/lui
    0x20, 0x21, 0x23, 0x24, 0x25, 0x27,          # lb/lh/lw/lbu/lhu/lwu
    0x28, 0x29, 0x2B, 0x2F, 0x37, 0x3F,          # sb/sh/sw/cache/ld/sd
    0x31, 0x35, 0x39, 0x3D,                      # lwc1/ldc1/swc1/sdc1
}


def mask_word(w):
    op = w >> 26
    if op in (0x02, 0x03):          # j / jal
        return w & 0xFC000000
    if op in IMM_OPS:
        return w & 0xFFFF0000
    return w


def masked_sig(data):
    n = len(data) - len(data) % WORD
    out = bytearray()
    for i in range(0, n, WORD):
        out += struct.pack(">I", mask_word(struct.unpack_from(">I", data, i)[0]))
    return bytes(out)


def parse_gga_syms(path):
    """Yield (name, vram, size, rom_off) for functions in ELF-dumped syms.toml."""
    sec_rom = sec_vram = None
    for line in path.read_text(errors="replace").splitlines():
        m = re.match(r'\s*rom = (0x[0-9A-Fa-f]+)', line)
        if m:
            sec_rom = int(m.group(1), 16)
            continue
        m = re.match(r'\s*vram = (0x[0-9A-Fa-f]+)', line)
        if m and sec_rom is not None and sec_vram is None:
            sec_vram = int(m.group(1), 16)
            continue
        if line.strip().startswith("[[section]]"):
            sec_rom = sec_vram = None
            continue
        m = re.match(r'\s*\{ name = "([^"]+)", vram = (0x[0-9A-Fa-f]+), size = (0x[0-9A-Fa-f]+) \}', line)
        if m and sec_rom is not None and sec_vram is not None:
            name, vram, size = m.group(1), int(m.group(2), 16), int(m.group(3), 16)
            yield name, vram, size, sec_rom + (vram - sec_vram)


def parse_mnsg_syms(path):
    for line in path.read_text(errors="replace").splitlines():
        m = re.match(r'\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(0x[0-9A-Fa-f]+)\s*;(.*)', line)
        if m and "type:func" in m.group(3):
            yield m.group(1), int(m.group(2), 16)


def main():
    root = Path(sys.argv[1])
    gga_rom = (root / "lib/gga/config/usa/baserom.decompressed.z64").read_bytes()
    mnsg_rom = (root / "mnsg.z64").read_bytes()
    gga_syms = list(parse_gga_syms(root / "lib/gga/config/usa/gga.elf.syms.toml"))
    mnsg_syms = list(parse_mnsg_syms(Path(sys.argv[2])))

    # MNSG is a plain ROM: the code segment loads at 0x80000400 from rom 0x1000.
    def mnsg_off(vram):
        return 0x1000 + (vram - 0x80000400)

    results = defaultdict(list)     # gga func name -> [mnsg names]
    reverse = defaultdict(list)     # mnsg name -> [gga func names]

    # group GGA functions by size so each MNSG address is read once per size
    by_size = defaultdict(list)
    for name, vram, size, off in gga_syms:
        if size < 8 or off + size > len(gga_rom):
            continue
        by_size[size].append((name, vram, off))

    for size, funcs in by_size.items():
        ref = {}
        for mname, mvram in mnsg_syms:
            mo = mnsg_off(mvram)
            if mo < 0 or mo + size > len(mnsg_rom):
                continue
            ref.setdefault(masked_sig(mnsg_rom[mo:mo + size]), []).append(mname)
        if not ref:
            continue
        for name, vram, off in funcs:
            hit = ref.get(masked_sig(gga_rom[off:off + size]))
            if hit:
                results[name] = hit
                for h in hit:
                    reverse[h].append(name)

    for gname in sorted(results, key=lambda n: results[n][0]):
        mnames = results[gname]
        amb = "" if len(mnames) == 1 else "  AMBIGUOUS"
        rev = reverse[mnames[0]]
        if len(rev) > 1 and not amb:
            amb = "  MULTI-TARGET(%d)" % len(rev)
        print("%-24s -> %s%s" % (gname, ",".join(mnames), amb))


main()
