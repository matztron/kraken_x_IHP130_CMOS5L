TEST_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROOT     := $(abspath $(TEST_DIR)/../..)

include $(ROOT)/test/mk/python.mk
include $(ROOT)/test/mk/cocotb.mk

TOPLEVEL ?= kraken_axil
MODULE   ?= test_axi_lite
FILELIST := $(ROOT)/test/filelist.f

.PHONY: all test sim clean check

all: test

check: check-python

test: check
	@echo "axi_lite: cocotb AXI4-Lite host tests (run make sim)"

sim: check-python
	@rtl=$$(awk '!/^[[:space:]]*#/ && NF {print}' $(FILELIST)); \
	srcs=""; for f in $$rtl; do srcs="$$srcs $(ROOT)/$$f"; done; \
	$(MAKE) cocotb-sim \
		TEST_DIR=$(TEST_DIR) \
		TOPLEVEL=$(TOPLEVEL) \
		MODULE=$(MODULE) \
		VERILOG_SOURCES="$$srcs"

clean:
	rm -rf sim_build results.xml __pycache__ *.vcd *.fst
	find $(TEST_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
