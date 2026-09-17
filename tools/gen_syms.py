#!/usr/bin/env python3
"""
Generate an N64Recomp symbol file (syms.toml) from splat's disassembly.

N64Recomp normally gets its symbols from a linked ELF via `--dump-context`,
which is how the Mystical Ninja Starring Goemon recompilation works: that
project is a decompilation, so it can link `build/usa/mnsg.elf` and read the
symbol table straight out of it.

Goemon's Great Adventure has no decompilation and therefore no ELF, so we
synthesize the same TOML directly from splat's output instead. Everything
required is already present in the disassembly:

  * splat emits matched `glabel` / `endlabel` pairs, so each function's extent
    is explicit rather than inferred from wherever the next label happens to
    start. This matters because the bytes between one function's `endlabel`
    and the next `glabel` are alignment padding and belong to no function --
    sizing by "next start minus this start" would silently absorb them.
  * every instruction carries a `/* ROM VRAM WORD */` comment, giving both
    address spaces without having to recompute them.

Section ROM/VRAM origins come from the splat config; a section's size is the
distance to the following segment, which keeps trailing padding inside the
section (matching how the reference project reports `.entry` as 0x50 for a
0x38-byte function).

LIMITATION: resident sections only. Overlays load to runtime-chosen addresses,
so their absolute references must be rewritten on load, and the relocation
table describing them exists only in a linked ELF (`ld --emit-relocs`). This
script cannot produce `relocs = [...]` entries, so overlay sections need a
different approach.

Usage:
    python tools/gen_syms.py config/usa/gga.splat.yaml -o config/usa/gga.syms.toml
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# `/* ROM VRAM WORD */  mnemonic ...`
INSN_RE = re.compile(r"/\*\s*([0-9A-Fa-f]+)\s+([0-9A-Fa-f]{8})\s+[0-9A-Fa-f]{8}\s*\*/")
GLABEL_RE = re.compile(r"^glabel\s+(\S+)")
ENDLABEL_RE = re.compile(r"^endlabel\s+(\S+)")

WORD = 4

# Names that are illegal or reserved in C. A function called `main` collides
# with C's entry point once N64Recomp emits the recompiled source.
C_RESERVED = {"main", "malloc", "free", "exit", "abort", "printf"}


class ConversionError(Exception):
    pass


def parse_functions(asm_path: Path) -> list[dict]:
    """
    Extracts functions from one splat-generated .s file.

    Returns a list of {name, vram, size} in file order. Instructions outside a
    glabel/endlabel pair (alignment padding) are ignored.
    """
    functions: list[dict] = []
    name: str | None = None
    first_vram: int | None = None
    last_vram: int | None = None

    for lineno, line in enumerate(asm_path.read_text().splitlines(), 1):
        m = GLABEL_RE.match(line)
        if m is not None:
            if name is not None:
                raise ConversionError(
                    f"{asm_path}:{lineno}: glabel {m.group(1)} while {name} is still open"
                )
            name, first_vram, last_vram = m.group(1), None, None
            continue

        m = ENDLABEL_RE.match(line)
        if m is not None:
            if name is None:
                raise ConversionError(f"{asm_path}:{lineno}: endlabel with no open glabel")
            if m.group(1) != name:
                raise ConversionError(
                    f"{asm_path}:{lineno}: endlabel {m.group(1)} closes {name}"
                )
            if first_vram is None:
                raise ConversionError(f"{asm_path}:{lineno}: {name} contains no instructions")
            functions.append(
                {"name": name, "vram": first_vram, "size": last_vram + WORD - first_vram}
            )
            name = None
            continue

        if name is None:
            continue  # padding or directives between functions

        m = INSN_RE.search(line)
        if m is not None:
            vram = int(m.group(2), 16)
            if first_vram is None:
                first_vram = vram
            last_vram = vram

    if name is not None:
        raise ConversionError(f"{asm_path}: {name} is never closed by an endlabel")

    return functions


def load_size_overrides(path: Path) -> dict[str, int]:
    """
    Reads `<function> <size>` lines correcting splat's function boundaries.

    splat finds function starts heuristically and sometimes splits one routine
    into two. N64Recomp catches this as "Unhandled branch ... to <addr>", where
    a branch target falls outside the function's declared range. The fix is to
    give the first function its true size; any function starting inside that
    range is then absorbed (see apply_size_overrides).
    """
    overrides: dict[str, int] = {}
    if not path.is_file():
        return overrides

    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ConversionError(f"{path}:{lineno}: expected '<function> <size>', got {raw!r}")
        overrides[parts[0]] = int(parts[1], 0)
    return overrides


def apply_size_overrides(
    functions: list[dict], overrides: dict[str, int]
) -> tuple[list[dict], list[str]]:
    """
    Applies size corrections and drops functions swallowed by a widened range.

    Returns (functions, absorbed_names).
    """
    result: list[dict] = []
    absorbed: list[str] = []
    covered_until = 0

    for fn in functions:
        if fn["vram"] < covered_until:
            absorbed.append(fn["name"])
            continue
        if fn["name"] in overrides:
            fn = dict(fn, size=overrides[fn["name"]])
            covered_until = fn["vram"] + fn["size"]
        result.append(fn)

    return result, absorbed


def code_sections(config: dict) -> list[dict]:
    """
    Pulls code segments out of the splat config, pairing each with the start of
    the following segment so a size can be computed.
    """
    segments = config["segments"]

    starts: list[int] = []
    for seg in segments:
        if isinstance(seg, list):
            starts.append(int(seg[0]))
        else:
            starts.append(int(seg["start"]))

    sections = []
    for i, seg in enumerate(segments):
        if isinstance(seg, list) or seg.get("type") != "code":
            continue
        if i + 1 >= len(starts):
            raise ConversionError(f"segment {seg.get('name')} has no following segment")
        sections.append(
            {
                "name": seg["name"],
                "rom": starts[i],
                "vram": int(seg["vram"]),
                "size": starts[i + 1] - starts[i],
            }
        )
    return sections


def main() -> int:
    ap = argparse.ArgumentParser(description="splat disassembly -> N64Recomp syms.toml")
    ap.add_argument("config", type=Path, help="splat yaml (e.g. config/usa/gga.splat.yaml)")
    ap.add_argument("-o", "--output", type=Path, required=True, help="syms.toml to write")
    ap.add_argument("--asm-dir", type=Path, default=None, help="override asm_path from config")
    ap.add_argument(
        "--size-overrides",
        type=Path,
        default=None,
        help="function size corrections (default: <config dir>/gga.size_overrides.txt)",
    )
    args = ap.parse_args()

    config = yaml.safe_load(args.config.read_text())
    base = args.config.parent.parent.parent  # config/<ver>/x.yaml -> repo root
    asm_dir = args.asm_dir or (base / config["options"]["asm_path"])

    overrides_path = args.size_overrides or (args.config.parent / "gga.size_overrides.txt")
    overrides = load_size_overrides(overrides_path)

    sections = code_sections(config)
    if not sections:
        raise ConversionError("no code segments found in config")

    out: list[str] = [
        "# Autogenerated from splat disassembly by tools/gen_syms.py",
        "# Resident sections only -- overlays need relocations, which require a linked ELF.",
        "",
    ]
    total_funcs = 0
    reserved_hits: list[str] = []
    applied_overrides: set[str] = set()

    for sec in sections:
        asm_path = asm_dir / (sec["name"] + ".s")
        if not asm_path.is_file():
            raise ConversionError(f"no disassembly for segment '{sec['name']}' at {asm_path}")

        functions = parse_functions(asm_path)
        functions, absorbed = apply_size_overrides(functions, overrides)
        for name in absorbed:
            print(f"    absorbed {name} into the preceding function (size override)")
        applied_overrides.update(f["name"] for f in functions if f["name"] in overrides)
        total_funcs += len(functions)

        sec_end = sec["vram"] + sec["size"]
        for fn in functions:
            if fn["name"] in C_RESERVED:
                reserved_hits.append(fn["name"])
            end = fn["vram"] + fn["size"]
            if fn["vram"] < sec["vram"] or end > sec_end:
                raise ConversionError(
                    f"{fn['name']} (0x{fn['vram']:08X}..0x{end:08X}) escapes section "
                    f"{sec['name']} (0x{sec['vram']:08X}..0x{sec_end:08X})"
                )

        out.append("[[section]]")
        out.append('name = ".' + sec["name"] + '"')
        out.append(f"rom = 0x{sec['rom']:08X}")
        out.append(f"vram = 0x{sec['vram']:08X}")
        out.append(f"size = 0x{sec['size']:X}")
        out.append("")
        out.append("functions = [")
        for fn in functions:
            out.append(
                '    { name = "' + fn["name"] + '", '
                + f"vram = 0x{fn['vram']:08X}, size = 0x{fn['size']:X} }},"
            )
        out.append("]")
        out.append("")

        print(
            f"  .{sec['name']:<8} rom 0x{sec['rom']:06X} vram 0x{sec['vram']:08X} "
            f"size 0x{sec['size']:<6X} {len(functions)} functions"
        )

    if reserved_hits:
        print(f"WARNING: names reserved in C: {sorted(set(reserved_hits))}", file=sys.stderr)

    unused = set(overrides) - applied_overrides
    if unused:
        raise ConversionError(
            f"{overrides_path} names functions that do not exist: {sorted(unused)}"
        )

    args.output.write_text("\n".join(out))
    print(f"wrote {args.output} ({len(sections)} sections, {total_funcs} functions)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ConversionError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
