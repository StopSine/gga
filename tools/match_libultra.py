#!/usr/bin/env python3
"""
Recover libultra function names for Goemon's Great Adventure by byte-matching
against Mystical Ninja Starring Goemon.

Why this is needed
------------------
N64Recomp's `reimplemented_funcs` interception is *name-based*: the runtime
supplies `<name>_recomp` and the recompiler redirects calls to it. GGA has no
decompilation, so its splat symbols are anonymous `func_<vram>_<rom>` and
nothing gets intercepted. Both games are the same engine on the same SDK, so
their libultra is byte-identical apart from addresses, and MNSG's symbols are
named -- which makes the names recoverable rather than guessable.

Matching
--------
Instruction words are compared with address-bearing fields masked out, since
the same routine linked at a different address differs only there:

  * j / jal          - the 26-bit target is masked
  * lui and the
    immediate ALU
    and load/store
    forms            - the 16-bit immediate is masked

Branches are PC-relative and so are compared intact, as are register fields.
That last point matters: several libultra primitives differ only by which
device register they touch (SI vs SP vs DP device-busy), so masking immediates
while keeping registers is what keeps them distinguishable. Where a masked
signature is still ambiguous, exact bytes are used to break the tie, and
anything still ambiguous is reported rather than guessed.

Safety
------
A name is only emitted if the runtime actually defines `<name>_recomp`.
Membership of `reimplemented_funcs` is not sufficient: naming a function the
runtime does not implement turns a working build into an undefined-reference
link error.
"""

from __future__ import annotations

import argparse
import struct
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

WORD = 4

# opcodes whose 16-bit immediate encodes an address or address-derived constant
IMM_OPS = {
    0x08, 0x09,        # addi, addiu
    0x0A, 0x0B,        # slti, sltiu
    0x0C, 0x0D, 0x0E,  # andi, ori, xori
    0x0F,              # lui
    0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26,  # lb lh lwl lw lbu lhu lwr
    0x28, 0x29, 0x2A, 0x2B, 0x2E,              # sb sh swl sw swr
    0x31, 0x35, 0x39, 0x3D,                    # lwc1 ldc1 swc1 sdc1
}
JUMP_OPS = {0x02, 0x03}  # j, jal


def mask_word(w: int) -> int:
    op = w >> 26
    if op in JUMP_OPS:
        return w & 0xFC000000
    if op in IMM_OPS:
        return w & 0xFFFF0000
    return w


def signatures(rom: bytes, off: int, size: int) -> tuple[bytes, bytes]:
    """Returns (masked, exact) byte signatures for a function."""
    exact = rom[off:off + size]
    masked = bytearray(len(exact))
    for i in range(0, size - size % WORD, WORD):
        struct.pack_into(">I", masked, i, mask_word(struct.unpack_from(">I", exact, i)[0]))
    return bytes(masked), bytes(exact)


def load(syms_path: Path, rom_path: Path, named_only: bool):
    """Yields (name, size, masked, exact) for every function in a syms file."""
    data = tomllib.loads(syms_path.read_text())
    rom = rom_path.read_bytes()
    out = []
    for sec in data["section"]:
        if "rom" not in sec:
            continue
        for fn in sec.get("functions", []):
            name = fn["name"]
            if named_only and name.startswith("func_"):
                continue
            off = sec["rom"] + (fn["vram"] - sec["vram"])
            size = fn["size"]
            if off + size > len(rom) or size < 8:
                continue
            masked, exact = signatures(rom, off, size)
            out.append((name, size, masked, exact, sec["name"], fn["vram"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="recover libultra names by byte-matching")
    ap.add_argument("--ref-syms", type=Path, required=True, help="MNSG syms.toml (named)")
    ap.add_argument("--ref-rom", type=Path, required=True, help="MNSG decompressed ROM")
    ap.add_argument("--syms", type=Path, required=True, help="GGA syms.toml (anonymous)")
    ap.add_argument("--rom", type=Path, required=True, help="GGA decompressed ROM")
    ap.add_argument("--safe-names", type=Path, required=True,
                    help="names the runtime actually implements as <name>_recomp")
    ap.add_argument("-o", "--output", type=Path, help="write renames here")
    ap.add_argument("--min-size", type=lambda v: int(v, 0), default=0x30,
                    help="below this size a masked match is not trusted; "
                         "exact bytes are required instead")
    ap.add_argument("--all", action="store_true",
                    help="also report matches outside the safe set (not applied)")
    args = ap.parse_args()

    safe = {l.strip() for l in args.safe_names.read_text().splitlines() if l.strip()}

    ref = load(args.ref_syms, args.ref_rom, named_only=True)
    tgt = load(args.syms, args.rom, named_only=False)
    print(f"reference named functions : {len(ref)}")
    print(f"target functions          : {len(tgt)}")

    # index the reference by (size, masked signature)
    by_sig: dict[tuple[int, bytes], list] = defaultdict(list)
    for name, size, masked, exact, _, _ in ref:
        by_sig[(size, masked)].append((name, exact))

    matched: dict[str, str] = {}
    ambiguous: list[tuple[str, list[str]]] = []
    too_small: list[str] = []
    collisions: dict[str, list[str]] = defaultdict(list)

    for name, size, masked, exact, sec, vram in tgt:
        cands = by_sig.get((size, masked))
        if not cands:
            continue
        names = sorted({n for n, _ in cands})
        if len(names) > 1:
            # fall back to exact bytes to separate register-distinguished twins
            exact_hits = sorted({n for n, e in cands if e == exact})
            if len(exact_hits) == 1:
                names = exact_hits
            else:
                ambiguous.append((name, names))
                continue

        # A short routine carries little information once immediates are
        # masked: a prologue, one jal and an epilogue is the shape of every
        # small wrapper in the library, so masked equality means nothing.
        # Demand exact bytes below the threshold.
        if size < args.min_size and not any(e == exact for _, e in cands):
            too_small.append(name)
            continue

        matched[name] = names[0]
        collisions[names[0]].append(name)

    # Require the mapping to be one-to-one. A reference name claiming several
    # targets means the signature failed to discriminate, so drop it entirely
    # rather than pick arbitrarily.
    dropped_multi = {}
    for ref_name, targets in collisions.items():
        if len(targets) > 1:
            dropped_multi[ref_name] = targets
            for t in targets:
                matched.pop(t, None)

    applied = {t: r for t, r in matched.items() if r in safe}
    held = {t: r for t, r in matched.items() if r not in safe}
    dupes = {}

    print()
    print(f"byte-matched              : {len(matched)}")
    print(f"  safe to apply           : {len(applied)}")
    print(f"  held (runtime lacks it) : {len(held)}")
    print(f"ambiguous (not applied)   : {len(ambiguous)}")
    print(f"rejected, too small       : {len(too_small)}")
    print(f"rejected, name->many      : {len(dropped_multi)}")
    for r, ts in list(dropped_multi.items())[:5]:
        print(f"    {r} matched {len(ts)} targets")

    if args.output:
        lines = [
            "# libultra names recovered by byte-matching against MNSG.",
            "# Only names the runtime implements as <name>_recomp are listed;",
            "# naming an unimplemented one turns interception into a link error.",
            "",
        ]
        for t, r in sorted(applied.items(), key=lambda kv: kv[1]):
            lines.append(f"{t} = {r}")
        args.output.write_text("\n".join(lines) + "\n")
        print(f"\nwrote {args.output} ({len(applied)} renames)")

    if args.all and held:
        print("\nheld names (byte-matched but not runtime-implemented):")
        for t, r in sorted(held.items(), key=lambda kv: kv[1])[:25]:
            print(f"  {r:<28} <- {t}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
