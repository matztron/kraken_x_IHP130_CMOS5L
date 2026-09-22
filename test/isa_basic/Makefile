# Capture this Makefile's directory before includes rewrite MAKEFILE_LIST.
TEST_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROOT     := $(abspath $(TEST_DIR)/../..)

include $(ROOT)/test/mk/pioasm.mk
include $(ROOT)/test/mk/python.mk
include $(ROOT)/test/mk/cocotb.mk

OUT_DIR := $(TEST_DIR)/generated
PIOS := $(wildcard $(TEST_DIR)/*.pio)
HEXS := $(patsubst $(TEST_DIR)/%.pio,$(OUT_DIR)/%.hex,$(PIOS))

TOPLEVEL ?= kraken_io
MODULE   ?= test_isa_basic
FILELIST := $(ROOT)/test/filelist.f

.PHONY: all assemble test sim clean check

all: test

check: check-pioasm check-python

assemble: check-pioasm $(HEXS)

$(OUT_DIR):
	mkdir -p $(OUT_DIR)

$(OUT_DIR)/%.hex: $(TEST_DIR)/%.pio | $(OUT_DIR)
	$(PIOASM) -o hex $< $@

test: check assemble
	@echo "isa_basic: hex ready ($(words $(HEXS)) programs)"

sim: assemble check-python
	@rtl=$$(awk '!/^[[:space:]]*#/ && NF {print}' $(FILELIST)); \
	srcs=""; for f in $$rtl; do srcs="$$srcs $(ROOT)/$$f"; done; \
	$(MAKE) cocotb-sim \
		TEST_DIR=$(TEST_DIR) \
		TOPLEVEL=$(TOPLEVEL) \
		MODULE=$(MODULE) \
		VERILOG_SOURCES="$$srcs"

clean:
	rm -rf $(OUT_DIR) sim_build results.xml __pycache__ *.vcd *.fst
	find $(TEST_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
