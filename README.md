# Goemon's Great Adventure Disassembly

Splat configuration, symbol files and tooling for Goemon's Great Adventure (USA), used by [GGA64Recomp](https://github.com/StopSine/GGA64Recomp) to statically recompile the game.

This is **not** a decompilation. Nothing here is compiled from C: the game has no decompilation project, so the recompilation works from disassembly and symbol names instead. What this repository produces is a decompressed ROM, the split disassembly, and a linked ELF whose symbols and relocations the recompiler reads.

It began as a fork of the [Mystical Ninja Starring Goemon decompilation](https://github.com/klorfmorf/mnsg), which is where the splat setup and the `rommy` compression tooling come from.

## Building

### Prerequisites

#### 1. Install `uv`
`uv` manages the Python tools and dependencies automatically. No manual Python setup is required.
*   **Windows:** `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
*   **macOS / Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`

#### 2. Install a MIPS toolchain
Only needed for `make elf`; decompressing the ROM does not require it.

**Debian/Ubuntu:**
```bash
sudo apt install build-essential git binutils-mips-linux-gnu
```

**Arch Linux:**
```bash
sudo pacman -S base-devel
# Install AUR package: mips64-elf-binutils
```

### Steps

#### 1. Place the baserom
Put your retail US ROM at `config/usa/baserom.z64`.

#### 2. Decompress it
```bash
make
```
This writes `config/usa/baserom.decompressed.z64`, along with `config/usa/rommy.yaml` describing how each file in the Nisitenma-Ichigo table was compressed.

**This is all a build of the parent repository needs.** The symbol files the recompiler reads (`config/usa/gga.elf.syms.toml` and `gga.elf.datasyms.toml`) are committed, so there is no need to split the ROM or link the ELF just to build the game.

### Regenerating the symbol files

Only necessary when the disassembly itself changes.

```bash
make setup   # split the ROM into asm/ and bin/
make elf     # assemble and link build/usa/gga.elf
```

The `--emit-relocs` on that final link is the point of the ELF: it preserves relocation records that disassembly alone cannot provide. Then, from the parent repository:

```bash
./N64Recomp --dump-context lib/gga/config/usa/gga.dump_context.toml
```

and its `dump.toml` / `data_dump.toml` become the two committed symbol files.

See [`docs/overlay_loader.md`](docs/overlay_loader.md) for how the overlays are handled and why they need this treatment.

### Development (Optional)
If you are editing the Python tools and want your editor to resolve their imports, run `uv sync` to create a standard `.venv` folder.
