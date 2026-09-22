# test/hello_world — PIO software + (later) cocotb HDL checks
#
#   make -C test/hello_world assemble
#   make -C test/hello_world test
#   make -C test/hello_world sim     # requires RTL in src/

# Capture this Makefile's directory before includes rewrite MAKEFILE_LIST.
TEST_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROOT     := $(abspath $(TEST_DIR)/../..)

include $(ROOT)/test/mk/pioasm.mk
include $(ROOT)/test/mk/python.mk
include $(ROOT)/test/mk/cocotb.mk

OUT_DIR := $(TEST_DIR)/generated
PIO_SRC := $(TEST_DIR)/hello_world.pio
HEX     := $(OUT_DIR)/hello_world.hex

PYTEST ?= $(PYTHON) -m pytest
PYTEST_ARGS ?= -q

TOPLEVEL ?= kraken_io
MODULE   ?= test_hello_world
FILELIST := $(ROOT)/test/filelist.f

.PHONY: all assemble test sim clean check

all: test

check: check-pioasm check-python

assemble: check-pioasm $(HEX)

$(OUT_DIR):
	mkdir -p $(OUT_DIR)

$(HEX): $(PIO_SRC) | $(OUT_DIR)
	$(PIOASM) -o hex $(PIO_SRC) $(HEX)
	@echo "assembled $(PIO_SRC) -> $(HEX)"

test: check assemble
	$(PYTEST) $(PYTEST_ARGS) $(TEST_DIR)/test_assemble.py

sim: assemble check-python
	@rtl=$$(awk '!/^[[:space:]]*#/ && NF {print}' $(FILELIST)); \
	if [ -z "$$rtl" ]; then \
		echo "sim: no RTL in test/filelist.f yet — skipping"; \
		exit 1; \
	fi; \
	srcs=""; \
	for f in $$rtl; do srcs="$$srcs $(ROOT)/$$f"; done; \
	$(MAKE) cocotb-sim \
		TEST_DIR=$(TEST_DIR) \
		TOPLEVEL=$(TOPLEVEL) \
		MODULE=$(MODULE) \
		VERILOG_SOURCES="$$srcs"

clean:
	rm -rf $(OUT_DIR) sim_build results.xml __pycache__ *.vcd *.fst
	find $(TEST_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
