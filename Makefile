# Goemon's Great Adventure (USA) disassembly.
#
# This is not a decompilation: nothing here is compiled from C. The targets
# produce what the recompilation in the parent repository consumes.
#
#   make            decompress the ROM -- all a build of the parent repo needs,
#                   since the symbol files it reads are committed
#   make setup      the above, then split the ROM into asm/ and bin/
#   make elf        assemble and link build/usa/gga.elf, which carries the
#                   symbols and relocations --dump-context reads
#
# Regenerating the committed symbol files is the one step left manual, because
# it needs N64Recomp from the parent repository:
#
#   ./N64Recomp --dump-context lib/gga/config/usa/gga.dump_context.toml
#
# and its dump.toml / data_dump.toml become config/usa/gga.elf.syms.toml and
# gga.elf.datasyms.toml.

VERSION ?= usa

CONFIG_DIR = config/$(VERSION)
BUILD_DIR  = build/$(VERSION)

UV     ?= uv
PYTHON ?= $(UV) run python
SPLAT  ?= $(UV) run splat

BASEROM      = $(CONFIG_DIR)/baserom.z64
DECOMPRESSED = $(CONFIG_DIR)/baserom.decompressed.z64
MANIFEST     = $(CONFIG_DIR)/rommy.yaml
SPLAT_YAML   = $(CONFIG_DIR)/gga.splat.yaml
ELF          = $(BUILD_DIR)/gga.elf

.PHONY: default all setup elf clean nuke

default: all

all: $(DECOMPRESSED)

# rommy writes the manifest as it goes, describing how each file in the
# Nisitenma-Ichigo table was compressed, so it is an output here rather than an
# input. Recompressing later reads it back.
$(DECOMPRESSED): $(BASEROM)
	$(PYTHON) tools/rommy.py decompress \
	    --input $(BASEROM) \
	    --output $(DECOMPRESSED) \
	    --manifest $(MANIFEST) \
	    --pad

# A recipe rather than $(error), which would abort while the rule is merely
# being considered, and a test rather than an unconditional failure, so that
# forcing a rebuild with -B does not trip over a ROM that is already in place.
$(BASEROM):
	@test -f $@ || { echo "Place your retail US ROM at $@" >&2; exit 1; }

setup: $(DECOMPRESSED)
	$(SPLAT) split $(SPLAT_YAML)

# Delegated to the script rather than inlined: it needs to walk splat's output,
# and the --emit-relocs on its final link is the whole reason the ELF exists.
elf: tools/build_elf.sh
	./tools/build_elf.sh

clean:
	rm -rf build

nuke: clean
	rm -rf asm bin .splat
	rm -f $(DECOMPRESSED) $(MANIFEST)
