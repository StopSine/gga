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
`type` attribute, `gga.undefined_syms.ld`, or a stale cache. Expect to leave
some symbols alone.

**Check the dumps, not `asm/`.** Grepping `asm/` for a `glabel` is a valid
check for a *function*, but it reports a false negative for a data symbol:
`player_slots` produced no `dlabel` in `asm/` yet came out renamed in
`data_dump.toml` and duly broke the patch build, which still said
`D_800883A0`. The dumps are what the build actually reads, so confirm there:

```bash
grep -c '<new name>' lib/gga/config/usa/gga.elf.syms.toml \
                     lib/gga/config/usa/gga.elf.datasyms.toml
```

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

## Naming libultra

A name in N64Recomp's `reimplemented_funcs` or `ignored_funcs`
(`N64RecompSource/src/symbol_lists.cpp`) is renamed to `<name>_recomp` and **its
body is never generated**. `reimplemented` means the runtime supplies the
replacement; `ignored` means nothing does, so the call must disappear along with
its caller.

That makes naming a subtree, not a function, the unit of work: pick a root the
runtime implements, name every interior function alongside it, and all the
interior bodies drop together with nothing left to reference them. Naming half a
subtree links against an undefined `<name>_recomp`, which is the failure to
expect. After regenerating, the check is:

```bash
grep -rhoE "\b(os|__os|gu)[A-Za-z_0-9]*_recomp\b" RecompiledFuncs/ | sort -u
```

Every name it prints must be defined in `src/`, `patches/` or the runtime.
`src/game/unknown_symbols.cpp` holds no-op definitions for the ones that are
genuinely inert.

### Recovering names from MNSG

Both games are the same engine on the same SDK, so their libultra is
byte-identical apart from addresses, and MNSG's symbols are named. Two matchers
exploit that:

* `tools/match_libultra.py` compares whole functions and needs a syms.toml for
  both sides.
* `tools/match_libultra_by_addr.py` needs only MNSG's `symbol_addrs.txt`, which
  gives name to address and no sizes. It takes each GGA function's size and
  compares that many bytes at each MNSG address, so identical routines still
  match:

```bash
curl -sLo /tmp/mnsg_syms.txt https://raw.githubusercontent.com/klorfmorf/mnsg/main/config/usa/symbol_addrs/symbol_addrs.txt
python lib/gga/tools/match_libultra_by_addr.py . /tmp/mnsg_syms.txt
```

Both mask address-bearing fields, which means they **cannot** tell apart
routines that differ only in which device register they touch --
`__osSiDeviceBusy`, `__osSpDeviceBusy` and `__osDpDeviceBusy` are one signature,
as are the Si and Sp raw IO pairs. Those are reported as AMBIGUOUS and must be
settled by reading the register out of the disassembly. Trust the register over
the matcher.

A no-match usually means the size differs between the two builds, not that the
routine is absent; those still have to be identified structurally, from the call
graph and the registers touched.

### Arity, when the matchers fail

None of the pak layer byte-matches, and prefix matching there is all false
positives -- generic prologues agree for about eleven words, so anything below
that threshold is noise and above it finds nothing. What settled it was counting
arguments, because libultra's `osPfs*` signatures have nearly unique arities
(`osPfsAllocateFile` takes seven, `osPfsDeleteFile` five, `osPfsFindFile` and
`osPfsReadWriteFile` six).

Read arity off the callee, not the call site. Take the frame size from the
opening `addiu $sp, $sp, -N`; the caller's stack pointer is then `$sp + N`, its
first four words are the `$a0`-`$a3` home slots, and a load at `$sp + N + 0x10`
or beyond is argument five onwards. Anything below `N` is a local or a saved
register. Counting `$aN` uses inside the body does not work -- every function of
any size uses all four as scratch.

The prologue also shows which arguments are real: a routine that spills `$a1`
and `$a2` to their home slots and never touches `$a3` takes three.

**The controller path is the worked example of why the unit is the subtree.**
`osContInit` was once withheld on purpose: intercepting it alone replaced the
function without establishing the state (`__osMaxControllers`, the PIF ram
template) that GGA's own still-unnamed `osContStartReadData` read, so the poll
block came out empty and the game queried the controller once and then sent
nothing. That was a half-named subtree, not a reason the path could not be
named.

The whole path is named now -- `osContInit`, `osContStartReadData`,
`osContGetReadData`, `osContStartQuery`, `osContGetQuery`, `__osMotorAccess`,
`__osContRamRead`, `__osContRamWrite` -- so the runtime owns it end to end and
nothing is left reading state the game no longer sets up. Naming any subset of
it again would reproduce the original bug.
