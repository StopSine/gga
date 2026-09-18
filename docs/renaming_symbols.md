# Renaming a symbol

Giving a routine a real name means regenerating the symbol files the
recompilation reads. `asm/` is **not** an input to the build, so editing
`config/usa/symbol_addrs/symbol_addrs.txt` alone changes nothing that runs — the
names travel:

```
symbol_addrs.txt -> splat -> asm/ + .splat/usa/gga.ld
                             |
                             +-> tools/build_elf.sh -> build/usa/gga.elf
                                                        |
                          N64Recomp --dump-context <-----+
                                    |
                                    +-> gga.elf.syms.toml, gga.elf.datasyms.toml
                                            |
                             N64Recomp <-----+  -> RecompiledFuncs/
```

Anything in the parent repository's `patches/` that names a symbol by its old
generated form stops resolving at the moment those files change, so a rename and
the patch edits are one change. `gga.patches.toml` sets `strict_patch_mode`, so
this fails loudly rather than producing a silently unpatched build.

## Prerequisites

* `uv`, which supplies splat — no separate install
* A MIPS toolchain for `build_elf.sh`. On Windows this lives in WSL:
  `sudo apt install binutils-mips-linux-gnu`. The Windows side has no MIPS
  assembler, so this step runs under `wsl`.
* `N64Recomp.exe` and `RSPRecomp.exe` at the parent repository root

## Steps

Declare the name, from `lib/gga`:

```
scene_apply_scissor = 0x800DEC40; // type:func
```

Split, which rewrites `asm/` and the linker script:

```bash
uv run splat split config/usa/gga.splat.yaml
```

Confirm the name actually applied, because splat may ignore it silently — see
the pitfalls below:

```bash
grep -rl "^glabel scene_apply_scissor$" asm/
```

Link the ELF. `--emit-relocs` inside the script is the point of it: the
relocation records are what disassembly alone cannot provide.

```bash
wsl -- bash -lc "cd /mnt/<path>/lib/gga && ./tools/build_elf.sh"
```

Dump the symbols, from the parent repository root. This writes `dump.toml` and
`data_dump.toml` into the working directory, whatever `output_func_path` says:

```bash
./N64Recomp.exe lib/gga/config/usa/gga.dump_context.toml --dump-context
```

Compare before installing. Normalise line endings first or every line appears to
have changed:

```bash
diff <(tr -d '\r' < lib/gga/config/usa/gga.elf.syms.toml) <(tr -d '\r' < dump.toml)
```

A rename should be two lines per symbol, at identical `vram` and `size`, moving
position because the list is name-sorted. Anything else deserves reading before
it is installed.

```bash
tr -d '\r' < dump.toml      > lib/gga/config/usa/gga.elf.syms.toml
tr -d '\r' < data_dump.toml > lib/gga/config/usa/gga.elf.datasyms.toml
rm dump.toml data_dump.toml
```

Update every use of the old name in `patches/`, then regenerate and build:

```bash
rm -rf RecompiledFuncs
./N64Recomp.exe lib/gga/config/usa/gga.recomp.toml
python lib/gga/tools/fix_zero_loads.py RecompiledFuncs
```

## Pitfalls

**splat ignores some declarations without saying so.** Seven of the first
fifteen took; the rest were dropped with splat exiting 0 and printing nothing.
It follows the address, not the name — the same address under a different name
is ignored too. Not caused by duplicate declarations, the size overrides, the
`type` attribute, `gga.undefined_syms.ld`, or a stale cache. Always grep `asm/`
to check, and expect to leave some symbols alone. The one data symbol that
applied, `gfx_context`, is also the only one splat emits into
`undefined_syms_auto.ld` as a cross-section reference, which may be why.

**`type:data` is not valid.** splat wants one of its known types (`func`, `u8`,
`s16`, `Vec3f`, …) or a custom type starting with a capital letter, so a
viewport is `type:Vp` and a display list `type:Gfx`. An invalid type aborts the
whole split with exit 2, naming the line.

**Size overrides at overlay addresses are unreliable.** Every overlay links at
`0x08000000`, so a bare `0x08001794` is ambiguous across all 311 of them. The
`size:0xF0` override for `func_08001794_660634` was honoured on one run and not
the next, which gave the function `0x3C` and made N64Recomp refuse it:

```
Failed to determine size of jump table at 0x0800C58C
```

That entry is currently corrected by hand in the generated
`gga.elf.syms.toml`. Check it after every regeneration. Overrides at
main-segment addresses have been reliable.

**`N64Recomp.exe` writes CRLF.** `.gitattributes` normalises on commit, but the
diff is unreadable until converted, hence the `tr -d '\r'` above.

**`fix_zero_loads.py` is not optional.** A load targeting `$zero` is lowered as
`0 = MEM_W(...)`, which does not compile. The pass rewrites those and fails if
any survive.
