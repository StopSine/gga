#!/usr/bin/env python3
"""Match GGA functions to MNSG names by longest common instruction prefix.

match_libultra_by_addr.py requires the two routines to be the same length, so
it finds nothing when the builds differ by a few instructions -- which is most
of the Pfs layer. This compares masked instruction words from the entry point
and keeps the longest agreement instead, which survives a differing tail.

A match is reported only when the prefix is long, the runner-up is clearly
shorter, and no other GGA function claims the same name as strongly. Those are
guards against coincidence, not proof: confirm anything acted on against the
call graph and the registers touched.
"""

import re
import struct
import sys
from pathlib import Path

WORD = 4
WINDOW = 96          # words compared at most
MIN_PREFIX = 22      # words that must agree; a generic prologue is ~11
MARGIN = 4           # words the best must beat the runner-up by

IMM_OPS = {
    0x08, 0x09, 0x0C, 0x0D, 0x0E, 0x0F,
    0x20, 0x21, 0x23, 0x24, 0x25, 0x27,
    0x28, 0x29, 0x2B, 0x2F, 0x37, 0x3F,
    0x31, 0x35, 0x39, 0x3D,
}


def mask_word(w):
    op = w >> 26
    if op in (0x02, 0x03):
        return w & 0xFC000000
    if op in IMM_OPS:
        return w & 0xFFFF0000
    return w


def words(rom, off, count):
    out = []
    for i in range(count):
        p = off + i * WORD
        if p + WORD > len(rom):
            break
        out.append(mask_word(struct.unpack_from(">I", rom, p)[0]))
    return out


def lcp(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def parse_gga_syms(path):
    sec_rom = sec_vram = None
    for line in path.read_text(errors="replace").splitlines():
        if line.strip().startswith("[[section]]"):
            sec_rom = sec_vram = None
            continue
        m = re.match(r'\s*rom = (0x[0-9A-Fa-f]+)', line)
        if m:
            sec_rom = int(m.group(1), 16)
            continue
        m = re.match(r'\s*vram = (0x[0-9A-Fa-f]+)', line)
        if m and sec_rom is not None and sec_vram is None:
            sec_vram = int(m.group(1), 16)
            continue
        m = re.match(r'\s*\{ name = "([^"]+)", vram = (0x[0-9A-Fa-f]+), size = (0x[0-9A-Fa-f]+) \}', line)
        if m and sec_rom is not None and sec_vram is not None:
            vram = int(m.group(2), 16)
            yield m.group(1), vram, int(m.group(3), 16), sec_rom + (vram - sec_vram)


def parse_mnsg_syms(path):
    for line in path.read_text(errors="replace").splitlines():
        m = re.match(r'\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(0x[0-9A-Fa-f]+)\s*;(.*)', line)
        if m and "type:func" in m.group(3):
            yield m.group(1), int(m.group(2), 16)


def main():
    root = Path(sys.argv[1])
    gga_rom = (root / "lib/gga/config/usa/baserom.decompressed.z64").read_bytes()
    mnsg_rom = (root / "mnsg.z64").read_bytes()
    gga = [f for f in parse_gga_syms(root / "lib/gga/config/usa/gga.elf.syms.toml")
           if f[0].startswith("func_")]
    ref = [(n, words(mnsg_rom, 0x1000 + (v - 0x80000400), WINDOW))
           for n, v in parse_mnsg_syms(Path(sys.argv[2]))]
    ref = [(n, w) for n, w in ref if len(w) >= MIN_PREFIX]

    best_for_name = {}
    rows = []
    for name, vram, size, off in gga:
        nwords = min(size // WORD, WINDOW)
        if nwords < MIN_PREFIX:
            continue
        w = words(gga_rom, off, nwords)
        scored = sorted(((lcp(w, rw), rn) for rn, rw in ref), reverse=True)
        top, runner = scored[0], (scored[1] if len(scored) > 1 else (0, ""))
        if top[0] < MIN_PREFIX or top[0] - runner[0] < MARGIN:
            continue
        rows.append((top[0], name, top[1], size))
        prev = best_for_name.get(top[1])
        if prev is None or top[0] > prev:
            best_for_name[top[1]] = top[0]

    for score, name, mname, size in sorted(rows, key=lambda r: -r[0]):
        tag = "" if best_for_name[mname] == score else "  (weaker claim on this name)"
        print("%-24s -> %-26s prefix=%-3d size=0x%X%s" % (name, mname, score, size, tag))


main()
