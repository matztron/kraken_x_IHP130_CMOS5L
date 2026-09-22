![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# Tiny Tapeout Verilog Project Template

- [Read the documentation for project](docs/info.md)

## What is Tiny Tapeout?

Tiny Tapeout is an educational project that aims to make it easier and cheaper than ever to get your digital and analog designs manufactured on a real chip.

To learn more and get started, visit https://tinytapeout.com.

## Set up your Verilog project

1. Add your Verilog files to the `src` folder.
2. Edit the [info.yaml](info.yaml) and update information about your project, paying special attention to the `source_files` and `top_module` properties. If you are upgrading an existing Tiny Tapeout project, check out our [online info.yaml migration tool](https://tinytapeout.github.io/tt-yaml-upgrade-tool/).
3. Edit [docs/info.md](docs/info.md) and add a description of your project.
4. Adapt the testbench to your design. See [test/README.md](test/README.md) for more information.

The GitHub action will automatically build the ASIC files using [LibreLane](https://www.zerotoasiccourse.com/terminology/librelane/).

## Enable GitHub actions to build the results page

- [Enabling GitHub Pages](https://tinytapeout.com/faq/#my-github-action-is-failing-on-the-pages-part)

## Resources

- [FAQ](https://tinytapeout.com/faq/)
- [Digital design lessons](https://tinytapeout.com/digital_design/)
- [Learn how semiconductors work](https://tinytapeout.com/siliwiz/)
- [Join the community](https://tinytapeout.com/discord)
- [Build your design locally](https://www.tinytapeout.com/guides/local-hardening/)

## What next?

- [Submit your design to the next shuttle](https://app.tinytapeout.com/).
- Edit [this README](README.md) and explain your design, how it works, and how to test it.
- Share your project on your social network of choice:
  - LinkedIn [#tinytapeout](https://www.linkedin.com/search/results/content/?keywords=%23tinytapeout) [@TinyTapeout](https://www.linkedin.com/company/100708654/)
  - Mastodon [#tinytapeout](https://chaos.social/tags/tinytapeout) [@matthewvenn](https://chaos.social/@matthewvenn)
  - X (formerly Twitter) [#tinytapeout](https://twitter.com/hashtag/tinytapeout) [@tinytapeout](https://twitter.com/tinytapeout)
  - Bluesky [@tinytapeout.com](https://bsky.app/profile/tinytapeout.com)



# KRAKEN IO PROCESSOR

![alt text](docs/img/kraken.png "Mascot of io processor ip")

## Design goal

This is a small and open IO processor implementation that can use the Raspberry Pi *pioasm* compiler to generate small programs to run on Kraken.

The goal is to have a small, portable and understandable learning project capable for ASIC and FPGA implementation.

It should be easily possible to scale the numbers of PIOs to use.

## Layout

| Path | Contents |
| --- | --- |
| `src/` | SystemVerilog RTL, including `kraken_pkg` and the TinyTapeout top `project.v` |
| `test/` | Per-testcase PIO software + pytest/cocotb (+ `test/mk` helpers) |

## Tooling

- **Simulator:** Cocotb + Verilator + [`cocotbext-axi`](https://github.com/alexforencich/cocotbext-axi). Verilator is taken from [oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build) when `/Applications/oss-cad-suite/bin` exists.
- **Assembler:** `submodules/pioasm-x`, built by the test Makefiles

Python deps (venv):

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Kraken simulation builds **pioasm** from `submodules/pioasm-x` and uses the venv packages above.

## Build & test

```bash
make help
make                    # assemble golden checks
make TEST=hello_world
make test-sim           # cocotb + Verilator (hello_world square wave)
make clean
```

First testcases:
- `test/hello_world/` — square wave (`SET` + delay)
- `test/isa_basic/` — JMP, WAIT, IN/OUT, PUSH/PULL, MOV, IRQ
- `test/features/` — side-set, FIFO join, STATUS, multi-SM host FIFOs
- `test/axi_lite/` — AXI4-Lite CSR host (`kraken_axil`)
- `test/clkdiv_axi/` — per-SM CLKDIV + EXEC/PIN banks (`NUM_SM=2`)
- `test/uart_axi/` — UART TX over AXI (`pioasm` + TXF0 → gpio0 8N1)
- `test/uart_rx_axi/` — UART RX over AXI (bit-bang gpio_in → RXF0)
- `test/tt_top/` — TinyTapeout top (`project.v`): pin host loads `hello_world.pio` and checks gpio0

## Documentation pointers

- **System architecture (SoC integration):** [`system_arch.md`](system_arch.md)
- **Support matrix (what works / what’s missing):** [`kraken_support.md`](kraken_support.md)
- Spec (encodings & target behavior): [`pio_derived_spec.md`](pio_derived_spec.md)
- **AXI-Lite CSR map:** [`docs/axil_csr_map.md`](docs/axil_csr_map.md)
- **Analog sidecar proposal:** [`kraken_analog_proposal.md`](kraken_analog_proposal.md)
- https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_pio
