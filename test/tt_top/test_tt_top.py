"""Chip-level tests: program the TinyTapeout top over the 2-wire host link."""

from __future__ import annotations

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

from lib.tt_serial import (
    CTRL,
    EXECCTRL,
    ID,
    ID_VALUE,
    SM_ADDR,
    KrakenSerial,
    load_hex,
)

TEST_DIR = Path(__file__).resolve().parent
HEX_PATH = TEST_DIR / "generated" / "hello_world.hex"

# wrap_bottom=0, wrap_top=1
EXECCTRL_WRAP1 = 0x0000_0020
# set_base=0, set_count=1 so SET drives gpio0
PINCTRL_SET1 = 0x0001_0000

SET_PINS_1 = 0xE001
SET_PINDIRS_1 = 0xE081
SET_PINDIRS_0 = 0xE080
JMP_PIN_5 = 0x00C5


@cocotb.test()
async def test_link_id_readback(dut):
    """A read frame returns the ID ROM, proving both link directions work."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    host = KrakenSerial(dut)
    await host.reset()

    assert await host.read(ID) == ID_VALUE

    # A write followed by a read must round-trip through the CSR file.
    await host.write(EXECCTRL, 0x0010_0A3E)
    assert await host.read(EXECCTRL) == 0x0010_0A3E


@cocotb.test()
async def test_tt_hello_world(dut):
    """hello_world.pio loaded over the link toggles gpio0 on uio[0]."""
    assert HEX_PATH.is_file(), f"missing {HEX_PATH}; run make assemble first"
    words = load_hex(HEX_PATH)
    assert words == [0xE101, 0xE100], [hex(w) for w in words]

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    host = KrakenSerial(dut)
    await host.reset()

    await host.load_imem(words)
    await host.configure_sm(0, execctrl=EXECCTRL_WRAP1, pinctrl=PINCTRL_SET1)
    await host.enable(0x1)

    samples = []
    for _ in range(16):
        await RisingEdge(dut.clk)
        samples.append(int(dut.uio_out.value) & 1)

    bits = "".join(str(b) for b in samples)
    assert "11001100" in bits or "00110011" in bits, f"gpio0 samples {samples}"


@cocotb.test()
async def test_bidirectional_pad_oe(dut):
    """SET PINDIRS drives and releases uio[0]; this is what open-drain I2C needs."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    host = KrakenSerial(dut)
    await host.reset()

    # Pads must come out of reset as inputs so nothing on the board is fought.
    assert host.gpio_oe() == 0, f"uio_oe not released after reset: {host.gpio_oe():#x}"

    await host.configure_sm(0, pinctrl=PINCTRL_SET1)

    # Forced SM_INSTR executes even with the SM disabled, so the pad state is
    # entirely under test control here.
    await host.exec_instr(SET_PINDIRS_1)
    assert host.gpio_oe() & 1 == 1, "SET PINDIRS,1 did not drive uio[0]"

    await host.exec_instr(SET_PINS_1)
    assert host.gpio_out() & 1 == 1, "SET PINS,1 did not set the uio[0] level"

    await host.exec_instr(SET_PINDIRS_0)
    assert host.gpio_oe() & 1 == 0, "SET PINDIRS,0 did not release uio[0]"


@cocotb.test()
async def test_input_pins_are_synchronised(dut):
    """A level on uio[1] reaches gpio[1] through the two-flop synchroniser.

    A forced SM_INSTR only moves the PC when the jump is taken, so JMP PIN with a
    non-zero target reports the pin level as a PC change.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    host = KrakenSerial(dut)
    await host.reset()

    # jmp_pin is EXECCTRL[14:10]; point it at gpio1.
    await host.configure_sm(0, execctrl=(1 << 10))

    host.set_gpio_in(uio=0b0000010)
    await ClockCycles(dut.clk, 4)
    await host.exec_instr(JMP_PIN_5)
    pc_high = await host.read(SM_ADDR)

    await host.write(CTRL, 1 << 4)  # SM_RESTART, back to PC 0
    host.set_gpio_in(uio=0b0000000)
    await ClockCycles(dut.clk, 4)
    await host.exec_instr(JMP_PIN_5)
    pc_low = await host.read(SM_ADDR)

    assert pc_high == 5, f"gpio1 high should take JMP PIN to 5, got {pc_high}"
    assert pc_low == 0, f"gpio1 low should not jump, got {pc_low}"
