# Shared cocotb + Verilator helpers.
# Including Makefile must set: ROOT, TOPLEVEL, MODULE, VERILOG_SOURCES
# Optional: TEST_DIR (defaults to cwd), SIM
#
# Always drive cocotb via $(PYTHON) from python.mk (prefer .venv). Do not trust
# whatever `cocotb-config` is first on PATH (e.g. oss-cad-suite Python 3.11).

SIM ?= verilator
TOPLEVEL_LANG ?= verilog
WAVES ?= 0

export SIM TOPLEVEL_LANG

COCOTB_MAKEFILES := $(shell $(PYTHON) -c "import cocotb_tools, pathlib; print(pathlib.Path(cocotb_tools.__file__).resolve().parent / 'makefiles')" 2>/dev/null)
ifeq ($(COCOTB_MAKEFILES),)
  COCOTB_MAKEFILES := $(shell $(PYTHON) -c "import cocotb, pathlib; print(pathlib.Path(cocotb.__file__).resolve().parent / 'share' / 'makefiles')" 2>/dev/null)
endif

# Resolve libpython / share from the same interpreter as $(PYTHON)
PYTHON_BIN := $(PYTHON)
LIBPYTHON_LOC := $(shell $(PYTHON) -m cocotb_tools.config --libpython 2>/dev/null)
export PYTHON_BIN LIBPYTHON_LOC

# Prefer venv binaries (cocotb-config) over oss-cad-suite on PATH
PYTHON_BINDIR := $(dir $(PYTHON))
export PATH := $(PYTHON_BINDIR):$(PATH)

# SystemVerilog + package support for Verilator
EXTRA_ARGS ?= -sv --timing
ifeq ($(WAVES),1)
  EXTRA_ARGS += --trace --trace-structs
endif

export EXTRA_ARGS

# Allow `from lib.sm_cfg import ...` in cocotb modules
export PYTHONPATH := $(ROOT)/test:$(PYTHONPATH)

.PHONY: cocotb-sim

cocotb-sim:
ifeq ($(COCOTB_MAKEFILES),)
	$(error cocotb makefiles not found; pip install cocotb in $(PYTHON))
endif
ifndef LIBPYTHON_LOC
	$(error could not resolve LIBPYTHON_LOC via '$(PYTHON) -m cocotb_tools.config --libpython')
endif
	@echo "cocotb: PYTHON_BIN=$(PYTHON_BIN)"
	@echo "cocotb: LIBPYTHON_LOC=$(LIBPYTHON_LOC)"
	@echo "cocotb: lib-dir=$$($(PYTHON) -m cocotb_tools.config --lib-dir)"
	cd $(TEST_DIR) && \
	$(MAKE) -f $(COCOTB_MAKEFILES)/Makefile.sim \
		SIM=$(SIM) \
		TOPLEVEL_LANG=$(TOPLEVEL_LANG) \
		TOPLEVEL=$(TOPLEVEL) \
		COCOTB_TOPLEVEL=$(TOPLEVEL) \
		COCOTB_TEST_MODULES=$(MODULE) \
		MODULE=$(MODULE) \
		VERILOG_SOURCES="$(VERILOG_SOURCES)" \
		EXTRA_ARGS="$(EXTRA_ARGS)" \
		PYTHON=$(PYTHON) \
		PYTHON_BIN=$(PYTHON_BIN) \
		LIBPYTHON_LOC=$(LIBPYTHON_LOC)
