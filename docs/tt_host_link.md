# TinyTapeout pin map and host link

**RTL:** `src/kraken_tt_host.sv` (pads) · `src/kraken_serial_host.sv` (link) · `src/kraken_sync2.sv` (input sync)
**Driver:** `test/lib/tt_serial.py`

TinyTapeout provides 8 dedicated inputs, 8 dedicated outputs, and 8 bidirectional
pins, and that count does not grow with tile area. Two pins carry a synchronous
host link; the remaining 22 belong to the PIO.

## 1. Pin map

| Pads | Role | Internal |
| --- | --- | --- |
| `ui[7]` | host `SCK` | — |
| `uio[7]` | host `SDIO`, bidirectional | — |
| `uio[6:0]` | PIO bidirectional, driven with `gpio_oe` | `gpio[6:0]` |
| `uo[7:0]` | PIO output only | `gpio[14:7]` |
| `ui[6:0]` | PIO input only | `gpio[21:15]` |

The bidirectional bank sits at the low indices so `pioasm` programs that assume
low pin numbers for SDA, SCL, or SPI work without renumbering. Pad index equals
`gpio` index in that bank.

Open-drain protocols work because `kraken_pins` maintains `gpio_oe` from
`SET PINDIRS`, `OUT PINDIRS`, and side-set with `SIDE_PINDIR`. Releasing a pin is
`oe=0`; driving low is `oe=1, out=0`. Both vectors reset to zero, so every pad
comes out of reset as an input.

`gpio[14:7]` is output only. Those indices read back the level Kraken drives, so
`WAIT PIN` and `IN PINS` on them see the driven value rather than a floating pad.
`gpio[21:15]` is input only; writes to those indices do not reach a pad.
`gpio[31:22]` is not bonded out and reads zero.

All pad inputs pass through a two-flop synchroniser, which adds two cycles of
input latency relative to the `kraken_axil`-level tests that drive `gpio_in`
directly.

## 2. Host link

A synchronous 2-wire link: `SCK` is an input, `SDIO` is bidirectional and half
duplex. The device samples `SDIO` on the rising edge of `SCK` and changes its own
output on the falling edge.

One frame is 56 bits, shifted MSB first:

| Bits | Contents |
| --- | --- |
| 55:48 | `{dir, 3'b000, addr[11:8]}`, `dir` 1 = write, 0 = read |
| 47:40 | `addr[7:0]` |
| 39:32 | turnaround; the host releases `SDIO`, the device takes it on reads |
| 31:0 | data, MSB first |

The address is a CSR byte offset; the low two bits are ignored. Writes always use
all four byte lanes.

On a read the CSR access starts at bit index 16, so the eight turnaround bits give
the bus time to answer before the device drives bit index 24. On a write the CSR
access is issued after the last data bit, so the host must leave a short gap
before the next frame.

`SCK` must stay at or below `clk/4`. After `IDLE_CYCLES` (default 64) with no
`SCK` edge the bit counter resets, so an aborted frame cannot desynchronise the
link permanently. The counter also wraps every 56 bits, so a host that starts
cleanly after reset stays in sync without needing the timeout.

Bulk program load is cheap: write `IMEM_ADDR` once, then stream words to
`IMEM_DATA`, which auto-increments. Program load is capped at 32 words today
because `IMEM_ADDR` is five bits wide, matching `IMEM_DEPTH`.

## 3. Driving it from a testbench

```python
from lib.tt_serial import KrakenSerial, CTRL, ID, ID_VALUE

host = KrakenSerial(dut)
await host.reset()

assert await host.read(ID) == ID_VALUE

await host.load_program(hex_path)              # pioasm -o hex straight into IMEM
await host.configure_sm(0, execctrl=..., pinctrl=...)
await host.enable(0x1)

host.set_gpio_in(uio=0b0000010)                # protocol input levels
level = host.gpio_out() & 1                    # pad view of gpio0
```

`KrakenSerial` owns `ui_in` and `uio_in` because `SCK` and `SDIO` share those
buses with the PIO input pins; drive protocol inputs through `set_gpio_in` rather
than assigning the buses directly.

`exec_instr` forces one instruction through `SM_INSTR`. It works while the state
machine is disabled, which makes it the simplest way to poke pad state from a
test. Note that a forced instruction only moves the PC when a jump is taken.
