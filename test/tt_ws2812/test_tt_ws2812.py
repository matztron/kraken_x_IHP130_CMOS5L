"""WS2812B on the chip top: push GRB pixels over the 2-wire link, check the pulse widths.

The data line is gpio0, which is a bidirectional pad (uio[0]), so this also
proves the program can drive a pad it first has to turn around.
"""

from __future__ import annotations

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from lib.sm_cfg import pack_clkdiv, pack_execctrl, pack_pinctrl, pack_shiftctrl
from lib.tt_serial import TXF0, KrakenSerial, PadTrace, encode_set_pindirs

HEX_PATH = Path(__file__).resolve().parent / "generated" / "ws2812.hex"

DATA_PIN = 0

# Must match the .define values in ws2812.pio.
T1, T2, T3 = 2, 5, 3
BIT_CYCLES = T1 + T2 + T3
HIGH_FOR_ONE = T1 + T2
HIGH_FOR_ZERO = T1


async def start_ws2812(dut, pixels: list[int]) -> tuple[KrakenSerial, PadTrace]:
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    host = KrakenSerial(dut)
    await host.reset()

    words = await host.load_program(HEX_PATH)
    assert len(words) == 4, f"ws2812.pio should be 4 instructions, got {len(words)}"

    await host.configure_sm(
        0,
        clkdiv=pack_clkdiv(1),
        execctrl=pack_execctrl(wrap_bottom=0, wrap_top=len(words) - 1),
        # Shift left so the 24-bit pixel leaves the OSR MSB first, and refill
        # automatically every 24 bits.
        shiftctrl=pack_shiftctrl(out_shiftdir=0, autopull=1, pull_thresh=24),
        # Side-set is the data line; OUT only touches X, so out_count stays 0.
        pinctrl=pack_pinctrl(
            set_base=DATA_PIN,
            set_count=1,
            sideset_base=DATA_PIN,
            sideset_count=1,
        ),
    )

    await host.exec_instr(encode_set_pindirs(1))
    assert host.gpio_oe() & (1 << DATA_PIN), "data pad should be an output before we start"

    for pixel in pixels:
        await host.write(TXF0, (pixel & 0xFFFFFF) << 8)  # left-aligned for a 24-bit pull

    trace = PadTrace(host)
    trace.start()
    await host.enable(0x1)
    return host, trace


def expected_runs(pixels: list[int]) -> list[int]:
    runs = []
    for pixel in pixels:
        for i in range(23, -1, -1):
            runs.append(HIGH_FOR_ONE if (pixel >> i) & 1 else HIGH_FOR_ZERO)
    return runs


@cocotb.test()
async def test_ws2812_single_pixel(dut):
    """One GRB pixel: 24 high pulses, long for 1 bits and short for 0 bits."""
    pixel = 0x00FF80  # green 0x00, red 0xFF, blue 0x80: a mix of both bit values
    host, trace = await start_ws2812(dut, [pixel])

    await ClockCycles(dut.clk, 24 * BIT_CYCLES + 4 * BIT_CYCLES)
    trace.stop()

    runs = trace.high_runs(DATA_PIN)
    want = expected_runs([pixel])
    assert runs[: len(want)] == want, (
        f"pulse widths for 0x{pixel:06X} mismatch\n expected {want}\n got      {runs}"
    )


@cocotb.test()
async def test_ws2812_two_pixels_back_to_back(dut):
    """Two pixels from the TX FIFO with no host intervention between them."""
    pixels = [0xFF0000, 0x0000FF]
    host, trace = await start_ws2812(dut, pixels)

    await ClockCycles(dut.clk, 48 * BIT_CYCLES + 4 * BIT_CYCLES)
    trace.stop()

    runs = trace.high_runs(DATA_PIN)
    want = expected_runs(pixels)
    assert len(runs) >= len(want), f"expected {len(want)} pulses, got {len(runs)}"
    assert runs[: len(want)] == want, (
        f"pulse widths mismatch\n expected {want}\n got      {runs[: len(want)]}"
    )


@cocotb.test()
async def test_ws2812_line_idles_low_after_pixel(dut):
    """When the FIFO runs dry the line must park low, which is the reset window."""
    host, trace = await start_ws2812(dut, [0x123456])

    await ClockCycles(dut.clk, 24 * BIT_CYCLES + 8 * BIT_CYCLES)
    trace.stop()

    tail = trace.bit(DATA_PIN)[-4 * BIT_CYCLES :]
    assert all(level == 0 for level in tail), f"line should idle low, got {tail}"
