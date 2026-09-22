# Kraken IO — Implementation Support Matrix

**Status:** living document (matches RTL as of 2026-08-10)  
**Companion:** behavioral / encoding target in [`pio_derived_spec.md`](pio_derived_spec.md)

This file answers: **what Kraken runs today**, and **what is still missing for full Raspberry Pi PIO-class functionality** (RP2040 PIO as the primary reference; RP2350 called out separately).

Kraken aims for **`pioasm` instruction-binary compatibility** for supported features — not a drop-in RP2040 MMIO / pad clone.

---

## 1. Snapshot

| Layer | State |
| --- | --- |
| Instruction ISA (8 opcodes) | **Largely complete** for common `pioasm` programs |
| Side-set, FJOIN, STATUS, multi-SM FIFOs | **Implemented** |
| Host / SoC integration (registers, clkdiv, GPIO mux) | **Partial** — AXI-Lite CSR (`kraken_axil`); Pico 16.8 per-SM clkdiv; no GPIOCTRL |
| Cycle-accurate parity vs RP2040 silicon | **Not claimed** |
| RP2350 PIO extras | **Out of scope** |
| Kraken Analog (DAC/comp sidecar) | **Proposed** — see [`kraken_analog_proposal.md`](kraken_analog_proposal.md) |

**Default build:** 1 SM, 32×16 IMEM, 32-bit datapath, 4+4 FIFOs (+ always-present join-8 storage). Flat ports on `kraken_io`; AXI-Lite host on `kraken_axil` (see [`docs/axil_csr_map.md`](docs/axil_csr_map.md)).

**Verified in sim:** `test/hello_world`, `test/isa_basic`, `test/features`, `test/axi_lite`, `test/clkdiv_axi`, `test/uart_axi`, `test/uart_rx_axi`.

---

## 2. Supported now

### 2.1 Instructions (`pioasm` 16-bit encodings)

| Opcode | Support | Notes |
| --- | --- | --- |
| `JMP` | Yes | ALWAYS, !X, X--, !Y, Y--, X!=Y, PIN, !OSRE |
| `WAIT` | Yes | GPIO, PIN (vs `in_base`), IRQ (+ relative index) |
| `IN` | Yes | PINS, X, Y, NULL, ISR, OSR; shift dir; bitcount 1..32 |
| `OUT` | Yes | PINS, X, Y, NULL, PINDIRS, PC, ISR, **EXEC**; shift dir |
| `PUSH` / `PULL` | Yes | IfFull / IfEmpty, Block / noblock; empty PULL copies X |
| `MOV` | Yes | Invert / reverse; STATUS src; PC dest; **EXEC** dest |
| `IRQ` | Yes | Set / clear / wait; relative IRQ index |
| `SET` | Yes | PINS, X, Y, PINDIRS |

Delay field: yes (0..31, reduced when side-set occupies MSBs).

### 2.2 Shift / FIFO / control features

| Feature | Support | Notes |
| --- | --- | --- |
| Wrap (`wrap_bottom` / `wrap_top`) | Yes | Ports (not memory-mapped EXECCTRL) |
| Autopush / autopull | Yes | Threshold encoding 0 ⇒ 32 |
| Side-set mandatory | Yes | `sideset_count`, `sideset_base` |
| Side-set optional (`SIDE_EN`) | Yes | `side_en` |
| Side-set → PINDIRS | Yes | `side_pindir` |
| Side-set on stall cycles | Yes | Per derived spec |
| Side-set wins over SET/OUT | Yes | Same SM, same cycle |
| FIFO join TX / RX | Yes | `fjoin_tx` / `fjoin_rx`; unused dir full+empty |
| `MOV STATUS` | Yes | `status_sel` TX/RX level vs `status_n` |
| Shared IRQ flags (8) | Yes | Block-level sticky flags |
| Multi-SM | Partial | Parameter `NUM_SM`; default **1**; tests use 2 |
| Per-SM host TX/RX FIFOs | Yes | Packed `tx_data[32*i +: 32]`, etc. |
| Highest-SM pin priority | Partial | Simple OE-preferring mux (not full GPIOCTRL) |
| Forced EXEC from program | Yes | `OUT EXEC` / `MOV EXEC` |
| IMEM load from host | Yes | Write port while SM disabled in tests |

### 2.3 Configuration surface (today)

All config is **parallel input ports** on `kraken_io` (suitable for cocotb / FPGA wiring). There is **no** Pico-compatible register file.

Config is **per-SM** for CLKDIV, EXECCTRL, SHIFTCTRL, and PINCTRL (AXI banks at `0x100+0x20*n`). Flat `kraken_io` ports are packed per-SM field buses. IMEM and IRQ flags remain shared.

### 2.4 What programs can reasonably run

Examples that fit the current engine:

- Blink / square wave (`SET` + delay)
- Bit-banged protocols using OUT/IN/WAIT/side-set (e.g. UART TX-style programs)
- FIFO-fed serializers / deserializers with PULL/PUSH or autopush/pull
- Multi-SM demos with shared IMEM (same program/config) and separate FIFOs

---

## 3. Missing or incomplete vs full Pi PIO

Legend: **Missing** = not in RTL · **Stub** = port/hook only · **Partial** = present but not Pi-complete · **N/A** = intentional non-goal for Kraken v0

### 3.1 Clocking

| Pi feature | Kraken | Gap |
| --- | --- | --- |
| Per-SM `CLKDIV` (16.8 int+frac) | **Done** | `kraken_clkdiv`; CSR `0x100+0x10n`; dither |
| `CLKDIV_RESTART` | **Done** | `CTRL[11:8]` SC pulse |
| Enable / restart semantics in `CTRL` | **Done** | `SM_ENABLE` + `SM_RESTART` + `CLKDIV_RESTART` |

### 3.2 Host / memory-mapped programming model

| Pi feature | Kraken | Gap |
| --- | --- | --- |
| `CTRL`, `FSTAT`, `FDEBUG`, `FLEVEL` | **Done** | AXI CSRs (`FDEBUG` W1C sticky) |
| `TXFx` / `RXFx` FIFO data regs | **Done** | Via AXI TXF/RXF |
| `IRQ0/1_INTE/INTF/INTS` | Partial | Single IE + force + `irq` line (not dual IRQ0/1) |
| `INSTR_MEM[0..31]` | Partial | IMEM_ADDR/DATA window (not full MMIO mirror) |
| Per-SM `CLKDIV`, `EXECCTRL`, `SHIFTCTRL`, `PINCTRL` | **Done** | AXI banks `0x100+0x20*n` |
| `SM_INSTR` forced exec from host | **Done** | `+0x10` in SM bank |
| `SM_ADDR` / PC readback | **Done** | `+0x14` in SM bank |
| DMA request / DREQ pacing | Missing | N/A until SoC integrate |
| Multiple PIO blocks (`pio0`/`pio1`) | Missing | Single `kraken_io` instance |

### 3.3 Pin / pad integration

| Pi feature | Kraken | Gap |
| --- | --- | --- |
| Per-GPIO `GPIO_CTRL` → which PIO SM | Missing | OR / priority merge of SM out/oe vectors |
| Input synchronizers + bypass | Missing | Raw `gpio_in` |
| Pad OE ownership vs CPU | N/A | Outside PIO IP |
| RP2040 30 vs our `GPIO_W=32` | Partial | Width OK; mux model differs |

### 3.4 Per-SM isolation

| Pi feature | Kraken | Gap |
| --- | --- | --- |
| Independent wrap / pinctrl / shiftctrl per SM | **Done** | Per-SM packed config |
| Independent clkdiv per SM | **Done** | Per-SM `clk_en` from `kraken_clkdiv` |
| Independent FJOIN / STATUS per SM | **Done** | Via per-SM SHIFTCTRL / EXECCTRL |

### 3.5 Behavioral / edge-case parity

| Area | Gap |
| --- | --- |
| Autopull / autopush corner cases | Implemented in a simple form; not audited against all Pico sticky cases |
| FIFO sticky underflow/overflow (`FDEBUG`) | **Done** | AXI `FDEBUG` W1C |
| IRQ → NVIC / CPU wake | Flags only; no interrupt controller |
| Side-set + delay encoding | Implemented; needs more directed tests vs `pioasm` corner counts |
| SM disable mid-instruction / clock-enable interaction | Simple: frozen when `enable=0` or `clk_en=0` |
| `WAIT` on IRQ with all polarity / clear interactions | Basic set/clear/wait; not exhaustively matched |
| Instruction memory concurrent fetch vs write | Combo read; write anytime (test discipline: load when halted) |

### 3.6 RP2350 / later PIO (explicitly out of scope)

- Extended GPIO count / bank bases beyond RP2040-style 32  
- Any RP2350-only opcode or EXECCTRL fields  
- Secure / TZ-related PIO controls  

---

## 4. Parameter defaults vs Raspberry Pi RP2040

| Parameter | RP2040 PIO block | Kraken default | Comment |
| --- | ---: | ---: | --- |
| State machines | 4 | **1** (`NUM_SM_DEFAULT`) | Build with `-GNUM_SM=4` possible; config still shared |
| IMEM depth | 32 | 32 | Match |
| FIFO depth | 4 (+ join 8) | 4 (+ join 8 storage) | Join always instantiated in RTL (area cost) |
| Data width | 32 | 32 | Match |
| IRQ flags | 8 | 8 | Match count; no CPU IRQ wiring |
| PIO blocks per chip | 2 | 1 IP | Instantiate twice for two blocks |

---

## 5. Roadmap (implementation-oriented)

Aligned with [`pio_derived_spec.md`](pio_derived_spec.md) §13, updated to reality:

| Phase | Content | Status |
| --- | --- | --- |
| 0 | IMEM, 1 SM, SET+delay, wrap, host load | **Done** |
| 1 | Full opcode set, FIFOs, WAIT, autopush/pull, side-set, EXEC from SM | **Done** |
| 1b | Practical protocol tests (UART TX/RX, etc.) | **Done** (UART TX + RX over AXI) |
| 2 | FJOIN, STATUS, rel IRQ, multi-SM FIFOs | **Done** (IRQ rel + FJOIN + STATUS) |
| 2b | AXI-Lite CSR host, Pico 16.8 clkdiv | **Done** (`kraken_axil`, per-SM clkdiv) |
| 2c | Per-SM config banks, host `SM_INSTR`, input sync | **Partial** (`SM_INSTR`/`SM_ADDR`/`SM_RESTART` done; input sync still missing) |
| 2d | FSTAT/FDEBUG completeness, IRQ to NVIC-style | **Partial** (FSTAT + FDEBUG + FLEVEL; IRQ still simple) |
| 3 | Multi-block, GPIOCTRL-style mux, RP2350 opts | **Missing / optional** |

---

## 6. Compatibility statement (honest)

| Claim | Verdict |
| --- | --- |
| “Runs `pioasm` hex for supported instructions” | **Yes**, for programs that only need features in §2 |
| “Drop-in replacement for RP2040 PIO peripheral” | **No** |
| “Same register addresses / SDK `hardware_pio` without shim” | **No** |
| “Identical timing to silicon including pads” | **No** |

Use a **thin host shim** (map SDK register writes → Kraken ports) if you want Pico SDK-shaped software on FPGA/ASIC.

---

## 7. Document history

| Version | Date | Notes |
| --- | --- | --- |
| 0.1 | 2026-08-10 | Initial support matrix vs Pi PIO |
