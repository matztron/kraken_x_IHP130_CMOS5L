# Locate Raspberry Pi pioasm.
#
# Override: make PIOASM=/path/to/pioasm

ifeq ($(origin PIOASM),undefined)
  ifneq ($(wildcard /Applications/pico-sdk-tools/pioasm/pioasm),)
    PIOASM := /Applications/pico-sdk-tools/pioasm/pioasm
  else
    PIOASM := pioasm
  endif
endif

export PIOASM

.PHONY: check-pioasm

check-pioasm:
	@command -v $(PIOASM) >/dev/null 2>&1 || { \
		echo "error: pioasm not found (PIOASM=$(PIOASM))"; \
		echo "  export PATH=\"/Applications/pico-sdk-tools/pioasm:\$$PATH\""; \
		echo "  or: make PIOASM=/path/to/pioasm"; \
		exit 1; \
	}
	@$(PIOASM) --version
