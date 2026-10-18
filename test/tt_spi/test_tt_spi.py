"""SPI master TX on the chip top: bytes in over the 2-wire link, mode-0 waveform out.

MOSI is gpio0 and SCK is gpio1, both on the bidirectional bank, so the test
samples MOSI exactly where a mode-0 slave would: on the rising edge of SCK.
"""

from __future__ import annotations

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from lib.sm_cfg import pack_clkdiv, pack_execctrl, pack_pinctrl, pack_shiftctrl
from lib.tt_serial import TXF0, KrakenSerial, PadTrace, encode_set_pindirs

HEX_PATH = Path(__file__).resolve().parent / "generated" / "spi_tx.hex"

MOSI_PIN = 0
SCK_PIN = 1
BIT_CYCLES = 2  # out + nop, one SM cycle each


async def start_spi(dut, payload: list[int]) -> tuple[KrakenSerial, PadTrace]:
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    host = KrakenSerial(dut)
    await host.reset()

    words = await host.load_program(HEX_PATH)
    assert len(words) == 2, f"spi_tx.pio should be 2 instructions, got {len(words)}"

    await host.configure_sm(
        0,
        clkdiv=pack_clkdiv(1),
        execctrl=pack_execctrl(wrap_bottom=0, wrap_top=len(words) - 1),
        # MSB first, and refill after every 8 bits so one word carries one byte.
        shiftctrl=pack_shiftctrl(out_shiftdir=0, autopull=1, pull_thresh=8),
        pinctrl=pack_pinctrl(
            out_base=MOSI_PIN,
            out_count=1,
            set_base=MOSI_PIN,
            set_count=2,  # covers MOSI and SCK for the forced pindirs below
            sideset_base=SCK_PIN,
            sideset_count=1,
        ),
    )

    await host.exec_instr(encode_set_pindirs(0b11))
    assert host.gpio_oe() & 0b11 == 0b11, "MOSI and SCK should both be outputs"

    for byte in payload:
        await host.write(TXF0, (byte & 0xFF) << 24)  # left-aligned for an 8-bit pull

    trace = PadTrace(host)
    trace.start()
    await host.enable(0x1)
    return host, trace


def bits_msb_first(payload: list[int]) -> list[int]:
    return [(byte >> i) & 1 for byte in payload for i in range(7, -1, -1)]


@cocotb.test()
async def test_spi_single_byte(dut):
    """0xA5 must appear on MOSI, MSB first, one bit per SCK rising edge."""
    payload = [0xA5]
    host, trace = await start_spi(dut, payload)

    await ClockCycles(dut.clk, 8 * BIT_CYCLES + 8)
    trace.stop()

    got = trace.sample_on_rising(SCK_PIN, MOSI_PIN)
    want = bits_msb_first(payload)
    assert got[: len(want)] == want, f"MOSI mismatch\n expected {want}\n got      {got}"


@cocotb.test()
async def test_spi_two_bytes_back_to_back(dut):
    """Autopull must stitch two FIFO words into one continuous 16-bit burst."""
    payload = [0xA5, 0x3C]
    host, trace = await start_spi(dut, payload)

    await ClockCycles(dut.clk, 16 * BIT_CYCLES + 8)
    trace.stop()

    got = trace.sample_on_rising(SCK_PIN, MOSI_PIN)
    want = bits_msb_first(payload)
    assert len(got) >= len(want), f"expected {len(want)} SCK edges, got {len(got)}"
    assert got[: len(want)] == want, (
        f"MOSI mismatch\n expected {want}\n got      {got[: len(want)]}"
    )


@cocotb.test()
async def test_spi_clock_parks_low_when_fifo_empties(dut):
    """An empty TX FIFO must stall on OUT with side 0, leaving SCK idle low."""
    host, trace = await start_spi(dut, [0xFF])

    await ClockCycles(dut.clk, 8 * BIT_CYCLES + 40)
    trace.stop()

    edges = trace.sample_on_rising(SCK_PIN, MOSI_PIN)
    assert len(edges) == 8, f"one byte should produce exactly 8 SCK pulses, got {len(edges)}"

    tail = trace.bit(SCK_PIN)[-16:]
    assert all(level == 0 for level in tail), f"SCK should park low, got {tail}"
