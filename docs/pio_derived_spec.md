# Kraken IO — Derived PIO Specification

**Status:** Draft v0.1  
**Goal:** A small, portable, understandable programmable I/O processor that accepts binaries produced by Raspberry Pi `pioasm`, suitable for FPGA and ASIC learning implementations.

This document defines **Kraken IO** semantics. Where encodings and behaviors match RP2040-class PIO, that is intentional so official tooling can assemble programs. This is an independent specification for an open implementation; it is not Raspberry Pi documentation and is not endorsed by Raspberry Pi Ltd.

---

## 1. Design goals

| Goal | Requirement |
| --- | --- |
| Tooling | Accept 16-bit instruction words from `pioasm` (hex / C-SDK / MicroPython outputs) without rewriting programs |
| Scale | Compile-time parameters for number of PIO blocks, state machines per block, instruction memory depth, FIFO depth, GPIO width |
| Clarity | One instruction = one cycle (unless stalled); cycle-accurate I/O |
| Portability | Synthesis-friendly HDL; no hard dependence on a host CPU ISA |
| Completeness | MVP runs real `pioasm` programs; full feature parity is optional and phased |

### Non-goals (v0.x)

- Full RP2040 / RP2350 SoC or MMIO register map compatibility
- DMA controller, USB, or host CPU
- Bit-identical silicon timing / pad electrical behavior
- RP2350-only PIO extensions unless explicitly opted in later

---

## 2. Architecture overview

```
                    ┌─────────────────────────────────────────┐
                    │              PIO block                  │
 Host / testbench ──┤  CFG + FIFO ports                       │
                    │                                         │
                    │   Instruction memory [0 .. IMEM-1]      │
                    │            ▲ ▲ ▲ ▲                      │
                    │            │ │ │ │  (shared, multi-read)│
                    │   ┌────────┴─┴─┴─┴────────┐             │
                    │   │  SM0  SM1  …  SM(N-1) │             │
                    │   └──────────┬────────────┘             │
                    │              │ pin level / OE / sample  │
                    └──────────────┼──────────────────────────┘
                                   ▼
                              GPIO[W-1:0]
```

### 2.1 Parameter defaults

| Parameter | Symbol | Default | Notes |
| --- | --- | --- | --- |
| PIO blocks | `NUM_PIO` | 1 | Scalable |
| State machines per block | `NUM_SM` | 4 | RP2040 uses 4 |
| Instruction memory depth | `IMEM_DEPTH` | 32 | Addresses 0..31; JMP target field is 5 bits |
| Instruction width | — | 16 | Fixed for `pioasm` |
| Data path width | `DATA_W` | 32 | ISR / OSR / FIFO word |
| TX / RX FIFO depth | `FIFO_DEPTH` | 4 | Per SM, each direction |
| GPIO width | `GPIO_W` | 32 | Pin indices 0..31 for WAIT GPIO / mapping |
| IRQ flags | `NUM_IRQ` | 8 | Shared within a PIO block |
| Clock divider | — | 16.8 fixed-point | Integer + fractional |

Implementations may reduce `NUM_SM`, `FIFO_DEPTH`, or `GPIO_W` for learning builds, but must document which `pioasm` programs become invalid.

### 2.2 State machine contents

Each state machine (SM) has:

- Program counter `PC` (log2 of `IMEM_DEPTH` bits)
- 16-bit instruction register / decoder
- Delay / side-set field interpretation (config-dependent)
- Scratch registers `X`, `Y` (32-bit)
- Input shift register `ISR` and output shift register `OSR` (32-bit)
- Shift counters for ISR / OSR (0..32)
- TX FIFO and RX FIFO
- Clock divider producing a per-cycle `clk_en`
- Pin mapping for OUT / SET / SIDESET / IN
- Stall conditions (WAIT, FIFO full/empty, autopush/autopull)

---

## 3. Execution model

1. On each system clock where the SM is enabled **and** `clk_en` is asserted:
   - Fetch instruction at `PC` (unless forced EXEC is pending)
   - Apply side-set (if any) on the first cycle of the instruction, including stall cycles
   - Execute the operation
   - If not stalled, consume any remaining delay cycles, then advance `PC`
2. Default `PC` advance: `PC = (PC + 1) % IMEM_DEPTH`, unless JMP / wrap / EXEC changes control flow.
3. Every instruction takes **exactly one execution cycle** unless it **stalls**. Delay cycles are idle after the instruction completes (and after stall clears).
4. Side-set always occurs on the first cycle of an instruction, even if that cycle stalls.

### 3.1 Stall sources

| Cause | Behavior |
| --- | --- |
| `WAIT` condition false | Hold `PC`; retry same instruction |
| Blocking `PUSH` and RX FIFO full | Stall |
| Blocking `PULL` and TX FIFO empty | Stall |
| Autopush when RX FIFO full | Stall |
| Autopull when TX FIFO empty on needed refill | Stall |
| `OUT`/`IN` with empty/full shift regs under auto modes | As configured (see §7) |

Delay countdown does **not** start until the stall clears.

---

## 4. Instruction encoding (tooling contract)

Instructions are **16-bit** little-documented field layout matching `pioasm` / Pico SDK encodings:

```
15 14 13 | 12 11 10  9  8 |  7  6  5 |  4  3  2  1  0
  opcode | delay / sideset |  arg1   |     arg2
```

| Opcode `[15:13]` | Mnemonic |
| ---: | --- |
| `000` | `JMP` |
| `001` | `WAIT` |
| `010` | `IN` |
| `011` | `OUT` |
| `100` | `PUSH` / `PULL` |
| `101` | `MOV` |
| `110` | `IRQ` |
| `111` | `SET` |

Bits `[12:8]` are the **delay / side-set** field (§5). Bits `[7:5]` and `[4:0]` are instruction-specific.

Bit counts encoded as 0 mean **32** for `IN` / `OUT`.

---

## 5. Delay and side-set

### 5.1 Delay

Without side-set, `[12:8]` is a delay of 0..31 cycles after the instruction executes.

When side-set uses `S` bits of this field, the remaining `5 - S` (or `4 - S` with optional side-set) bits encode delay.

### 5.2 Side-set configuration (per SM)

| Config | Meaning |
| --- | --- |
| `SIDESET_COUNT` | Number of side-set data bits (0..5) |
| `SIDE_EN` | If 1, MSB of delay/sideset field is an “enable” bit (optional side-set); max data bits 4 |
| `SIDE_PINDIR` | If 1, side-set drives pin directions; else pin levels |
| `SIDESET_BASE` | Lowest GPIO index for side-set |

Side-set writes up to `SIDESET_COUNT` contiguous GPIOs starting at `SIDESET_BASE`, concurrent with the main op.

**Priority on the same pin, same cycle:** side-set wins over SET/OUT from the same SM. Across SMs, highest-numbered SM wins (RP2040-compatible arbitration). Document if a build uses a simpler arbiter.

---

## 6. Instruction reference

### 6.1 `JMP` — opcode `000`

```
[7:5] = condition
[4:0] = absolute address in instruction memory
```

| Cond | Meaning |
| ---: | --- |
| `000` | Always |
| `001` | `!X` (X == 0) |
| `010` | `X--` (X != 0, then X = X - 1) |
| `011` | `!Y` |
| `100` | `Y--` |
| `101` | `X != Y` |
| `110` | Pin (mapped jump pin) == 1 |
| `111` | `!OSRE` (OSR not empty enough / shift count not exhausted — OSR empty for further OUT) |

If condition true: `PC = addr`. Else: fall through. Delay always applies after the cycle.

> Note: assembled JMP addresses are absolute in IMEM. Host loaders must relocate when loading a program at a non-zero offset (as Pico SDK does).

### 6.2 `WAIT` — opcode `001`

```
[7]   = polarity (1 = wait for 1, 0 = wait for 0)
[6:5] = source
[4:0] = index
```

| Src `[6:5]` | Wait until |
| ---: | --- |
| `00` | Absolute GPIO `index` equals polarity |
| `01` | Pin at `PINCTRL_IN_BASE + index` equals polarity |
| `10` | IRQ flag `index` (with optional relative addressing encoding in index) equals polarity |
| `11` | Reserved / implementation-defined (RP2350 adds JMPPIN variants — defer) |

Stalls while condition is false.

### 6.3 `IN` — opcode `010`

```
[7:5] = source
[4:0] = bit_count (0 ⇒ 32)
```

| Src | Data |
| ---: | --- |
| `000` | `PINS` (mapped IN bus) |
| `001` | `X` |
| `010` | `Y` |
| `011` | `NULL` (zeros) |
| `100` | Reserved |
| `101` | Reserved |
| `110` | `ISR` |
| `111` | `OSR` |

Shift `bit_count` bits into ISR per `SHIFTCTRL_IN_SHIFTDIR` (left or right). Update ISR shift count. If autopush enabled and threshold reached: push ISR to RX FIFO, clear ISR and count (may stall if FIFO full).

### 6.4 `OUT` — opcode `011`

```
[7:5] = destination
[4:0] = bit_count (0 ⇒ 32)
```

| Dst | Effect |
| ---: | --- |
| `000` | `PINS` |
| `001` | `X` |
| `010` | `Y` |
| `011` | `NULL` (discard) |
| `100` | `PINDIRS` |
| `101` | `PC` (jump to shifted address) |
| `110` | `ISR` |
| `111` | `EXEC` (execute shifted word as instruction next cycle) |

Shift `bit_count` bits from OSR to destination. Autopull may refill OSR when threshold reached.

`OUT EXEC`: the `OUT` takes one cycle; the executee runs on the following execution cycle. Delay on the `OUT` itself is ignored; the executee may have delay.

### 6.5 `PUSH` / `PULL` — opcode `100`

Distinguished by bit 7 of the instruction (SDK: `PULL` encodings set the bit corresponding to `0x0080` in the base opcode word).

**PUSH**

```
[7]   = 0
[6]   = IfFull
[5]   = Block
[4:0] = 0 (unused)
```

- Push ISR → RX FIFO; clear ISR and input shift count.
- If `IfFull`: only push if shift count ≥ push threshold.
- If `Block`: stall when FIFO full; else non-blocking (no state change / drop per Pico semantics for non-blocking full — implement Pico-compatible behavior).

**PULL**

```
[7]   = 1
[6]   = IfEmpty
[5]   = Block
[4:0] = 0
```

- Pull TX FIFO → OSR; reset output shift count as full (32 bits remaining).
- If `IfEmpty`: only pull if OSR shift count ≥ pull threshold (OSR “empty enough”).
- Non-blocking empty: behave as `MOV OSR, X` (Pico-compatible).

### 6.6 `MOV` — opcode `101`

```
[7:5] = destination
[4:3] = operation
[2:0] = source
```

| Op `[4:3]` | Transform |
| ---: | --- |
| `00` | None |
| `01` | Invert |
| `10` | Bit-reverse |
| `11` | Reserved |

| Dest / Src codes | Register |
| ---: | --- |
| `000` | `PINS` |
| `001` | `X` |
| `010` | `Y` |
| `011` | `NULL` (src only; dest invalid) |
| `100` | `EXEC` (dest) / reserved (src) |
| `101` | `STATUS` (src) / `PC` (dest) |
| `110` | `ISR` |
| `111` | `OSR` |

`MOV EXEC`: like `OUT EXEC` — MOV in one cycle, executee next.  
`MOV PC`: unconditional jump.  
`STATUS`: all-ones or all-zeros from FIFO level compare vs `EXECCTRL_STATUS_SEL` / `STATUS_N`.

### 6.7 `IRQ` — opcode `110`

```
[7]   = 0 (reserved / clear encoding layout per Pico)
[6]   = Clear (1 = clear flag, 0 = set)
[5]   = Wait (stall until flag clear after set — “wait for clear”)
[4:0] = irq index (+ relative mode bit encoding)
```

Modulo-add relative IRQ indexing with SM number (low 2 bits) when the relative bit is set, matching Pico programs that use `rel`.

Flags 0..3 may be exported to host IRQ lines; 4..7 are SM-local to the block.

### 6.8 `SET` — opcode `111`

```
[7:5] = destination
[4:0] = immediate data (0..31)
```

| Dst | Effect |
| ---: | --- |
| `000` | `PINS` (mapped SET pins) |
| `001` | `X` |
| `010` | `Y` |
| `011` | Reserved |
| `100` | `PINDIRS` |
| others | Reserved |

---

## 7. Shift registers, autopush, autopull

### 7.1 Directions

- `SHIFTCTRL_IN_SHIFTDIR` / `OUT_SHIFTDIR`: 0 = shift left (MSB in/out first), 1 = shift right (LSB first) — match Pico field polarity in implementation notes when wiring CFG.
- Counters track bits shifted in/out; range 0..32.

### 7.2 Thresholds

- `PUSH_THRESH` / `PULL_THRESH`: 1..32 (encoding 0 means 32 in hardware config, same as Pico).
- **Autopush:** after `IN`, if count ≥ threshold, push ISR to RX and clear.
- **Autopull:** before/with `OUT` when remaining bits &lt; needed, refill from TX.

MVP may implement autopush/autopull as mandatory once enabled; deferred edge cases must be listed in the test plan.

### 7.3 FIFO join

Optional `FJOIN_TX` / `FJOIN_RX`: merge both 4-deep FIFOs into one 8-deep FIFO in one direction. Other direction becomes unusable (appear full and empty).

---

## 8. Program wrap

Per SM:

- `WRAP_TOP`: after executing this address, next `PC` becomes `WRAP_BOTTOM` instead of `+1` (when not jumping).
- `WRAP_BOTTOM`: wrap target.

Defaults: bottom = 0, top = `IMEM_DEPTH - 1` (or last instruction of loaded program as set by host).

Wrap is free (no extra cycle), unlike an explicit `JMP`.

---

## 9. Clock divider

Per SM, 16.8 divider:

- Effective rate ≈ `f_sys / (int + frac/256)`
- `int = 0` encoding means 65536 (Pico-compatible) — document in CFG
- Fractional division uses first-order dither (extend some periods by 1) for average rate

On cycles without `clk_en`, the SM does not advance; FIFOs remain host-accessible.

---

## 10. Pin mapping

Per SM `PINCTRL`-equivalent fields:

| Field | Role |
| --- | --- |
| `OUT_BASE` / `OUT_COUNT` | Contiguous OUT PINS / data |
| `SET_BASE` / `SET_COUNT` | Contiguous SET (count 0..5) |
| `SIDESET_BASE` / `SIDESET_COUNT` | Side-set |
| `IN_BASE` | Rotates GPIO sample bus so bit0 = `GPIO[IN_BASE]` |

Each SM may sample all GPIOs and drive mapped subsets. Output level and OE are separate registers.

Optional: 2-FF input synchronizers on GPIO samples (recommended; adds 2-cycle input latency).

---

## 11. Forced EXEC / debug

| Mechanism | Behavior |
| --- | --- |
| Host write to `SM_INSTR` | Execute that instruction immediately; `PC` unchanged unless instr modifies PC; ignore delay; ignore clock divider for this forced issue |
| `OUT EXEC` / `MOV EXEC` | Latched instruction executes on next SM cycle |

MVP should support host `SM_INSTR` for bring-up tests.

---

## 12. Host interface (Kraken-native)

Kraken does **not** require the RP2040 address map. A simple CFG/FIFO port is enough:

| Port / register (logical) | Access | Purpose |
| --- | --- | --- |
| `IMEM[addr]` | W | Load 16-bit instructions |
| `CLKDIV` | RW | Per-SM divider |
| `EXECCTRL` | RW | Wrap, side-set enables, status sel, JMP pin, etc. |
| `SHIFTCTRL` | RW | Autopush/pull, thresholds, directions, FJOIN |
| `PINCTRL` | RW | Pin bases/counts |
| `ADDR` | R | Current PC |
| `INSTR` | RW | Forced exec / read current instr |
| `TXF` / `RXF` | W/R | FIFO data |
| `FSTAT` / `FDEBUG` | R/W1C | FIFO status / sticky errors |
| `CTRL` | RW | SM enable bits, restart, clkdiv restart |
| `IRQ` / `IE` / `INTF` | RW | Flag and interrupt control |

Exact bitfields can mirror Pico for easier mental mapping, or use a simplified layout with a thin shim. Publish a register PDF/header once frozen.

---

## 13. Feature phases

### Phase 0 — Skeleton

- 1 SM, IMEM, SET PINS + delay, wrap, basic pin out
- Host load + enable
- Cocotb: blink / square-wave from `pioasm -o hex`

### Phase 1 — MVP (most `pioasm` teaching examples)

- All 9 opcodes with encodings in §4–§6
- X/Y, ISR/OSR, TX/RX FIFOs
- WAIT GPIO / PIN / IRQ
- Side-set (mandatory and optional)
- Autopush / autopull
- Clock divider (integer first; fractional next)
- Multi-SM (2–4) with shared IMEM
- Forced EXEC

### Phase 2 — Compatibility hardening

- FIFO join
- STATUS source
- Relative IRQ
- Input sync bypass
- SM priority arbitration matching Pico
- Fractional clkdiv dither
- More than one PIO block instance

### Phase 3 — Optional extensions (not required for Pi tooling)

- Wider GPIO banks with base offset (RP2350-style)
- Extra WAIT sources
- Deeper IMEM (breaks plain 5-bit JMP unless banked)

---

## 14. Compatibility statement

| Aspect | Kraken stance |
| --- | --- |
| Instruction binary | **Compatible** with `pioasm` 16-bit output for Phase 1 feature set |
| Assembly source | Unmodified `.pio` files preferred |
| Register map | **Not** required to match RP2040; shim optional |
| Timing | Cycle-accurate at SM instruction level when `clk_en=1`; pad/I/O fabric may differ |
| RP2350 extras | Out of scope until explicitly versioned |

Test strategy: assemble official / pico-examples PIO programs with `pioasm`, load hex into Kraken, compare SM pin traces and FIFO traffic against a reference model or RP2040 where available.

---

## 15. Tooling workflow

```text
program.pio  --(pioasm -o hex)-->  program.hex  -->  IMEM load  -->  SM run
             --(pioasm -o c-sdk)--> headers for host C tests (optional)
```

Simulation: **Verilator** + **cocotb** (see README).

---

## 16. Legal / attribution notes

- Instruction encodings and behavioral compatibility targets are informed by publicly documented Raspberry Pi PIO programming models and BSD-licensed SDK headers (`pio_instructions.h`, `pioasm`).
- Raspberry Pi product documentation remains under its own licenses; do not vendor modified datasheets into this tree.
- Kraken is an independent open learning implementation. Trademark names “Raspberry Pi” / “Pico” must not imply endorsement.
- Patent landscape around PIO-like interfaces may affect commercial distribution; this spec does not grant any patent license.

---

## 17. Open questions

1. Freeze register bitfields: Pico-mirror vs minimal Kraken map?
2. Phase 0 GPIO width: 8 vs 32?
3. Single shared IRQ space vs per-block only?
4. Formal golden model language: Python / cocotb scoreboard vs HDL twin?
5. Track RP2350 PIO version as `KRAKEN_PIO_VERSION` later?

---

## Document history

| Version | Date | Notes |
| --- | --- | --- |
| 0.1 | 2026-08-10 | Initial derived spec: ISA, features, phases |
| 0.2 | 2026-08-10 | See also [`kraken_support.md`](kraken_support.md) for RTL support vs Pi PIO gaps |
