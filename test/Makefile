# Run every testcase under test/<name>/
#
#   make -C test
#   make -C test TEST=hello_world

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)

include $(ROOT)/test/mk/pioasm.mk
include $(ROOT)/test/mk/python.mk

TEST_DIRS := $(wildcard $(ROOT)/test/*/Makefile)
ifeq ($(TEST),)
  RUN_DIRS := $(TEST_DIRS)
else
  RUN_DIRS := $(ROOT)/test/$(TEST)/Makefile
endif

.PHONY: all test test-assemble test-sim clean help

all: test

help:
	@echo "test/ targets:"
	@echo "  make / make test     run all test/*/Makefiles"
	@echo "  make TEST=name       run only test/<name>"
	@echo "  make test-assemble   assemble + golden checks only"
	@echo "  make test-sim        cocotb sims (per testcase)"
	@echo "  make clean"

test: check
	@for mk in $(RUN_DIRS); do \
		dir=$$(dirname $$mk); \
		echo "==> $$(basename $$dir)"; \
		$(MAKE) -C $$dir test \
			PIOASM=$(PIOASM) PYTHON=$(PYTHON) ROOT=$(ROOT) || exit 1; \
	done

test-assemble: check
	@for mk in $(RUN_DIRS); do \
		dir=$$(dirname $$mk); \
		echo "==> $$(basename $$dir) assemble"; \
		$(MAKE) -C $$dir assemble test \
			PIOASM=$(PIOASM) PYTHON=$(PYTHON) ROOT=$(ROOT) || exit 1; \
	done

test-sim: check-python
	@for mk in $(RUN_DIRS); do \
		dir=$$(dirname $$mk); \
		echo "==> $$(basename $$dir) sim"; \
		$(MAKE) -C $$dir sim \
			PIOASM=$(PIOASM) PYTHON=$(PYTHON) ROOT=$(ROOT) || exit 1; \
	done

check: check-pioasm check-python

clean:
	@for mk in $(TEST_DIRS); do \
		$(MAKE) -C $$(dirname $$mk) clean; \
	done
	find $(ROOT)/test -type d -name sim_build -exec rm -rf {} + 2>/dev/null || true
	find $(ROOT)/test -name results.xml -delete 2>/dev/null || true
