# Kraken IO RTL (SystemVerilog)

Single-cycle-style PIO state machine. Shared constants live in `pkg/kraken_pkg.sv`.

| File | Role |
| --- | --- |
| `../pkg/kraken_pkg.sv` | Opcodes, widths, types, decode helpers |
| `kraken_imem.sv` | Shared instruction memory |
| `kraken_decode.sv` | Instruction decode |
| `kraken_alu.sv` | ALU (pass/dec/add/sub) |
| `kraken_regfile.sv` | X, Y, ISR, OSR |
| `kraken_pc.sv` | PC register |
| `kraken_pins.sv` | SET/OUT pin mapping |
| `kraken_fifo.sv` | TX/RX FIFOs (+ join storage) |
| `kraken_clkdiv.sv` | Per-SM Pico 16.8 clock enable (frac dither) |
| `kraken_sm.sv` | SM control (fetch/exec/delay/wrap) |
| `kraken_pio.sv` | IMEM + SMs |
| `kraken_io.sv` | Flat-port top |
| `kraken_axil.sv` | AXI4-Lite CSR host + per-SM clkdiv |

Phase-1 ISA: `JMP`, `WAIT`, `IN`, `OUT`, `PUSH`/`PULL`, `MOV`, `IRQ`, `SET` (+ delay/wrap).
