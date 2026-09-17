#!/usr/bin/env python3
"""
Rewrite assignments to the zero register in N64Recomp's generated C.

MIPS $zero is hardwired to 0, and a load that targets it (`lw $zero, ...`) is a
legitimate way to touch memory while discarding the result -- games use it to
force a read. N64Recomp lowers the destination register literally, producing

    0 = MEM_W(ctx->r4, 0X0);

which is not assignable and fails to compile. The read still has to happen,
because the address may be a hardware register where the access itself is the
point, so the fix is to keep the expression and discard its value:

    (void)(MEM_W(ctx->r4, 0X0));

Run over RecompiledFuncs/ after N64Recomp and before compiling. The pass
asserts that no assignment to 0 survives, so a pattern it does not recognise
fails loudly here rather than as a compile error later.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# `0 = <expr>;` possibly indented. The expression runs to the final semicolon
# on the line, which is how N64Recomp emits these.
ASSIGN_RE = re.compile(r"^(\s*)0 = (.+);\s*$")
# Any surviving assignment to a literal zero, used as the post-condition.
RESIDUAL_RE = re.compile(r"(^|[^\w.>])0\s*=\s*[^=]")


def fix_file(path: Path) -> int:
    text = path.read_text(errors="ignore")
    if "0 = " not in text:
        return 0

    out = []
    fixed = 0
    for line in text.splitlines(keepends=True):
        m = ASSIGN_RE.match(line.rstrip("\n"))
        if m:
            indent, expr = m.group(1), m.group(2)
            newline = "\n" if line.endswith("\n") else ""
            out.append(f"{indent}(void)({expr});{newline}")
            fixed += 1
        else:
            out.append(line)

    if fixed:
        path.write_text("".join(out))
    return fixed


def main() -> int:
    ap = argparse.ArgumentParser(description="rewrite `0 = expr;` to `(void)(expr);`")
    ap.add_argument("directory", type=Path, help="directory of generated C (RecompiledFuncs)")
    ap.add_argument("--glob", default="*.c", help="files to process (default: *.c)")
    args = ap.parse_args()

    if not args.directory.is_dir():
        print(f"error: {args.directory} is not a directory", file=sys.stderr)
        return 1

    total = 0
    touched = 0
    for path in sorted(args.directory.glob(args.glob)):
        n = fix_file(path)
        if n:
            touched += 1
            total += n

    print(f"  rewrote {total} zero-register assignments across {touched} files")

    # Post-condition: nothing of the form `0 = ...` may remain.
    residual = []
    for path in sorted(args.directory.glob(args.glob)):
        for lineno, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            if RESIDUAL_RE.search(line) and "(void)" not in line:
                residual.append(f"{path.name}:{lineno}: {line.strip()}")

    if residual:
        print(f"error: {len(residual)} assignments to 0 remain:", file=sys.stderr)
        for r in residual[:10]:
            print(f"  {r}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
