# Build and use the pioasm-x compiler in submodules/pioasm-x.
#
# Override: make PIOASM=/path/to/pioasm

PIOASM_SRC   := $(ROOT)/submodules/pioasm-x/tools/pioasm
PIOASM_BUILD := $(ROOT)/submodules/pioasm-x/build
PIOASM_LOCAL := $(PIOASM_BUILD)/pioasm
PIOASM_VERSION := $(shell awk '/^[[:space:]]*set\(PICO_SDK_VERSION_MAJOR /{m=$$NF} /^[[:space:]]*set\(PICO_SDK_VERSION_MINOR /{n=$$NF} /^[[:space:]]*set\(PICO_SDK_VERSION_REVISION /{r=$$NF} END{gsub(/\)/,"",m); gsub(/\)/,"",n); gsub(/\)/,"",r); print m"."n"."r}' $(ROOT)/submodules/pioasm-x/pico_sdk_version.cmake)

ifeq ($(origin PIOASM),undefined)
  PIOASM := $(PIOASM_LOCAL)
endif

export PIOASM

.PHONY: check-pioasm pioasm-build

$(PIOASM_LOCAL): $(PIOASM_SRC)/CMakeLists.txt $(PIOASM_SRC)/main.cpp $(PIOASM_SRC)/pio_assembler.cpp
	@command -v cmake >/dev/null 2>&1 || { echo "error: cmake is required to build pioasm-x"; exit 1; }
	cmake -S $(PIOASM_SRC) -B $(PIOASM_BUILD) -DPIOASM_VERSION_STRING=$(PIOASM_VERSION)
	cmake --build $(PIOASM_BUILD)

ifeq ($(PIOASM),$(PIOASM_LOCAL))
pioasm-build: $(PIOASM_LOCAL)
check-pioasm: pioasm-build
else
pioasm-build:
check-pioasm:
endif

check-pioasm:
	@test -x "$(PIOASM)" || { \
		echo "error: pioasm not found (PIOASM=$(PIOASM))"; \
		echo "  expected build: $(PIOASM_LOCAL)"; \
		exit 1; \
	}
	@"$(PIOASM)" --version
