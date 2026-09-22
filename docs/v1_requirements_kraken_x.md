# Kraken X 
This is a requirements, spec and architecture document for Kraken X.
Kraken-X is a PIO machine capable of more complex protocols.

Kraken-X is compatible with pioasm-x compiler.
This is derived from Raspberry Pi version ("pioasm")

# Background
This is done on behalf on the challenge here:
https://blog.janestreet.com/protocol-emulator-asic-competition/

# Requirements

> The protocol emulator should be a unit facilitating arbitrary UART, I2C, GPIO, VGA, JTAG, SWD, CAN, SD-card, ws2812b communications

> The protocol emulator design should as a stretch support a low-speed Ethernet protocol (10BASE-T). This is done by MII. RMII is only an option if a pin-constrained version is needed. The PHY is seperate. This should act similar to a MAC unit. It must handle the ethernet frames in a meaningful way.

> The driver for the architecture should be MII ethernet (stretch goal) and most importantly UART/WS2812B/I2C/SPI. With the other protocols as a nice to have.

> The constraints of TinyTapeout (pinout, area) apply. The design is allowed to occupy 6x4 tiles (24 tiles). One tile can hold approx. 1000 flip-flops. Potentially 8x4 tiles are possible - see for email communication.

> The process node for tapeout is IHP’s 130nm CMOS5L process.

> It is desirable to be able run pioasm programs on kraken-x. Thus pioasm is a subset of pioasm-x

> Verification for each interface, sub-block etc shall be done with cocotb and fpga prototypes

> Host side protocol shall be AXI-lite however if Janestreet uses Wishbone then switch to wishbone is done.

# Architecture

The kraken-x protocol emulator must be more capable than the current Raspberry Pi PIO machines. So far I am considering the following modifications:

> IMEM: Increase IMEM side by a lot using an OpenRAM SRAM macro. The raspberry pi pico has a 4 read- / 1-write port RAM. This might be difficult to do with OpenRAM so having a RAM per Kraken-X PIO state machine. Decission is for a shared OpenRAM 256×16, 1R1W + fetch arbiter.

> FIFO depth is changed to 16 and same shape as on raspberry PIO.

> There will be a central packet/frame buffer with 1 KB of size to hold ethernet frames or images for output.

> Opcodes should stay single cycle but we most certainly need to add some more opcodes. These could be the following ones:

> The number of collaborative PIO SM units is 2. They are able to sync with peers via IRQs. If area permits this can be extended to 4 units.

> **DMA (in host bridge)**
> - Paths: (1) system → IMEM program load; (2) Packet SRAM ↔ SM TX/RX FIFOs.
> - Programmed by host via CSR descriptors: `src`, `dst`, `len`, `dir`, `sm_sel`.
> - Completion: sticky IRQ / status bit; SM may WAIT that IRQ. No scatter-gather in v1.

> Program is written to IMEM via system interface. for the tinytapeout version there will need to be a bitserial mode to get the data into the memory.



## Additional opcodes
For  UART, I2C, GPIO, VGA, JTAG, MII-10 we do not need new opcodes.
However for other protocols it can be helpful to have:

> **LJMP / CALL / RET** — for programs larger than 32 instructions (classic
> `JMP` only encodes a 5-bit address). Needed so 256×16 IMEM is usable for
> structured MII/VGA/CAN state machines without bank hacks.

> **DMA-kick** — SM or host starts a descriptor (Packet SRAM ↔ TX/RX FIFO).
> Pair with **WAIT DMA done** / IRQ so the SM can pace frames without the
> host on every word. Prefer CSR+IRQ in v0; optional 1-instr kick in pioasm-x.

# Architecture diagram

```text
       TT / Wishbone / __AXI-lite__
                    │
       ┌────────────▼─────────────┐
       │ Host bridge              │
       │  · CSR (load/run/cfg)    │
       │  · DMA engine            │
       │    - IMEM fill           │
       │    - Packet SRAM ↔ FIFOs │
       └───┬──────────┬───────┬───┘
           │          │       │ cfg / clear / read FCS
 program   │          │       │
           ▼          ▼       ▼
    ┌──────────┐ ┌─────────┐ ┌──────────────┐
    │ IMEM SRAM│ │ Packet  │ │ CRC sidecar  │
    │  256×16  │ │ SRAM    │ │ CRC32 (+opt) │
    └────┬─────┘ │ frames/ │ │ LFSR + mode  │
         │ fetch │ lines   │ └──────▲───────┘
         │       └────┬────┘        │
         │            │             │ feed data
┌────────┴────────┐   │             │
│ SM0 … SM1       │◄──┘             │
│ + TX/RX FIFOs   │                 │
│ + IRQ sync      │── OUT/shift ────┤  (TX feed:
│ (+ SM2..SM3)    │                 │   FIFO/OUT path)
│ if area permits │◄─ IN/MOV CRC ───┤  (read FCS /
│                 │                 │   clear via MOV)
└────────┬────────┘── IN bits ──────┘  (RX feed:
         │                              sample path)
         │ per-SM gpio_out / oe / in
         ▼
┌─────────────────┐
│ Pinmux/GPIOCTRL │  pad ownership, 2FF sync, TT map
└────────┬────────┘
         ▼
       pads
```

## Eth CRC in HW / CAN CRC in SW
CRC is a shifted peripheral like a pin.
This is less impressive than a CRC done by PIO itself but could help to reach Ethernet ("ETH_CRC") functionality. For CAN the CRC (CRC15) could be done by PIO -> a compromise/hybrid.
CRC works as a LFSR on the data path.

Example how to work with CRC (acts like a pin):
```text
// read residue / clear-init
MOV X, CRC / MOV CRC, NULL

// shift bits into engine
OUT CRC, n or feed on every OUT PINS when crc_en

// read final FCS to OSR/FIFO
IN CRC, 32 once
```

## Clocks
Single core `clk` for SMs, DMA, CSR. 
Per-SM integer (or 16.8) `clk_en` for bit rate. 
MII `TX_CLK`/`RX_CLK` (2.5 MHz @ 10M) are **pin inputs**; SMs WAIT
on edges (no second PLL required in v1). All async inputs 2FF-synced in pinmux.

## Host CSR (byte offsets, draft)

| Offset | Name | Role |
| ---: | --- | --- |
| 0x000 | CTRL | SM enable, soft reset, DMA start |
| 0x004 | STATUS | FIFO levels, DMA done, CRC error |
| 0x008 | IRQ / IE | W1C flags + enables |
| 0x010+ | TXFn / RXFn | SM FIFO data |
| 0x020 | IMEM_ADDR/DATA | Program window (or DMA-only load) |
| 0x040 | DMA_SRC/DST/LEN/CTRL | Descriptor |
| 0x060 | CRC_CTRL / CRC_DATA | mode, clear, read FCS |
| 0x080+ | SMn_* | EXEC/SHIFT/PIN/CLKDIV (Pico-shaped) |
| 0x0C0 | PINMUX | per-pad SM sel / OE |

## Area budget (6×4 ≈ 24k logic cells + macros; indicative)

| Block | Budget (logic cells) | Notes |
| --- | ---: | --- |
| 2× SM + FIFOs16 | 6–8k | Dominates soft logic |
| Host/CSR/DMA | 1–2k | Bus wrapper small vs CSR |
| Pinmux + sync | 0.5–1k | |
| CRC32 | 0.3–0.6k | |
| Margin / clk / misc | 2–3k | |
| **OpenRAM IMEM 256×16** | macro | Must fit TT SRAM flow |
| **OpenRAM packet 1 KB** | macro | |

Re-synth after each block; cut packet RAM or SM features before cutting UART demos.

## Priority

| Tier | Content |
| --- | --- |
| **Must** | 2 SMs; pioasm subset; AXI-Lite host (WB if TT requires); UART + WS2812 + I2C + SPI demos; FIFO depth 16; shared 256×16 IMEM; cocotb + FPGA |
| **Should** | 1 KB packet SRAM; DMA; pinmux + input sync; bit-serial IMEM load for TT |
| **Stretch** | MII @ 10 Mbps Ethernet frames; HW CRC32 sidecar; 4th SM if area allows |
| **Non-goals** | RGMII/GbE; HDMI; hardwired full MAC; RMII unless pads force it; large new ISA |