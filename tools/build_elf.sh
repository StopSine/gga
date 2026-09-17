#!/bin/bash
# Assemble splat's output and link an ELF, mirroring how mnsg builds one.
# The point is `--emit-relocs`: that is what preserves the relocation records
# N64Recomp's --dump-context needs and which disassembly alone cannot provide.
set -e

# Run from the repository root.
cd "$(dirname "$0")/.."

AS=mips-linux-gnu-as
LD=mips-linux-gnu-ld
# -march=vr4300 (not vr4300) so opcodes like `pref` assemble. Data misread as
# code can decode to MIPS-IV instructions; this ELF only exists to carry
# symbols and relocations, so accepting them is harmless and the bytes round
# trip unchanged.
ASFLAGS="-EB -mtune=vr4300 -march=vr4300 -mabi=32 -Iinclude -I."

rm -rf build/usa
mkdir -p build/usa

# splat puts data/rodata subsegments in subdirectories, so recurse.
while IFS= read -r f; do
    mkdir -p "build/usa/$(dirname "$f")"
    echo "  AS  $f"
    $AS $ASFLAGS -o "build/usa/$f.o" "$f"
done < <(find asm -name '*.s' | sort)

while IFS= read -r f; do
    mkdir -p "build/usa/$(dirname "$f")"
    echo "  BIN $f"
    $LD -r -b binary -o "build/usa/$f.o" "$f"
done < <(find bin -name '*.bin' | sort)

echo "  LD  build/usa/gga.elf"
$LD -T .splat/usa/gga.ld \
    -Map build/usa/gga.map \
    -T .splat/usa/undefined_syms_auto.ld \
    -T .splat/usa/undefined_funcs_auto.ld \
    -T config/usa/gga.undefined_syms.ld \
    --no-check-sections \
    --emit-relocs \
    -o build/usa/gga.elf

echo "=== result ==="
ls -l build/usa/gga.elf
echo "relocation sections:"
mips-linux-gnu-readelf -S build/usa/gga.elf | grep -oE "\.rel\.\S+" | sort -u
echo "total relocation entries:"
mips-linux-gnu-readelf -r build/usa/gga.elf | grep -cE "^[0-9a-f]{8}"
