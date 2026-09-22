TEST_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROOT     := $(abspath $(TEST_DIR)/../..)

include $(ROOT)/test/mk/pioasm.mk
include $(ROOT)/test/mk/python.mk
include $(ROOT)/test/mk/cocotb.mk

OUT_DIR := $(TEST_DIR)/generated
PIO_SRC := $(TEST_DIR)/uart_rx.pio
HEX     := $(OUT_DIR)/uart_rx.hex

TOPLEVEL ?= kraken_axil
MODULE   ?= test_uart_rx_axi
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
	@echo "uart_rx_axi: hex ready — run make sim"

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
