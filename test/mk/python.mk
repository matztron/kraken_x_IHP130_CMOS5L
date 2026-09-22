# Prefer project virtualenv Python when present.
# Expects ROOT to be set to the repository root by the including Makefile.

ifeq ($(ROOT),)
  $(error ROOT must be set to the Kraken IO repository root before including python.mk)
endif

ifeq ($(origin PYTHON),undefined)
  ifneq ($(wildcard $(ROOT)/.venv/bin/python),)
    PYTHON := $(ROOT)/.venv/bin/python
  else
    PYTHON := python3
  endif
endif

export PYTHON

.PHONY: check-python

check-python:
	@$(PYTHON) -c "import pytest" 2>/dev/null || { \
		echo "error: pytest not available for $(PYTHON)"; \
		echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; \
		exit 1; \
	}
	@$(PYTHON) -c "import cocotbext.axi" 2>/dev/null || { \
		echo "error: cocotbext-axi not available for $(PYTHON)"; \
		echo "  $(PYTHON) -m pip install -r $(ROOT)/requirements.txt"; \
		exit 1; \
	}
	@$(PYTHON) -c "import sys; print('python', sys.version.split()[0], '->', sys.executable)"
