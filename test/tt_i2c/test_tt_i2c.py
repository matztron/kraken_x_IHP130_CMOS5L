"""I2C master on the chip top, against an open-drain bus model with a tiny slave.

This is the test that actually needs gpio_oe on the pads: SDA and SCL are only
ever pulled down, never driven high, so the program depends on uio_oe reaching
uio[1:0]. The bus model supplies the pull-ups the silicon does not have.
"""

from __future__ import annotations

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

from lib.sm_cfg import pack_clkdiv, pack_execctrl, pack_pinctrl, pack_shiftctrl
from lib.tt_serial import RXF0, TXF0, KrakenSerial

HEX_PATH = Path(__file__).resolve().parent / "generated" / "i2c_min.hex"

SDA_PIN = 0
SCL_PIN = 1

# The program parks at `pull` (index 1) and the STOP sequence ends the loop.
WRAP_BOTTOM = 1
TRANSFER_CYCLES = 220  # START + 8 bits + ACK + STOP at clkdiv 1, with margin


def i2c_word(byte: int) -> int:
    """Left-align and invert a byte for OUT PINDIRS: a 1 bit must release SDA."""
    return (~byte & 0xFF) << 24


class I2cBus:
    """Pull-up model plus just enough slave to sample one byte and ACK it.

    A wire reads high unless the master or the slave pulls it down. The slave
    samples SDA on each SCL rising edge and, after the eighth bit, holds SDA low
    for one SCL period to acknowledge.
    """

    SDA = 1 << SDA_PIN
    SCL = 1 << SCL_PIN

    def __init__(self, host: KrakenSerial, *, ack: bool = True):
        self.host = host
        self.ack = ack
        self.bytes: list[int] = []
        self.saw_start = False
        self.saw_stop = False
        self.scl_rises = 0
        self.driven_high: list[int] = []  # open-drain violations by the master
        self._bits: list[int] = []
        self._slave_low = 0
        self._acking = False
        self._task = None

    def start(self) -> None:
        self._task = cocotb.start_soon(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.kill()
            self._task = None

    def _wires(self) -> int:
        oe = int(self.host.dut.uio_oe.value) & 0x7F
        out = int(self.host.dut.uio_out.value) & 0x7F
        if oe & out & (self.SDA | self.SCL):
            self.driven_high.append(oe & out)
        return 0x7F & ~((oe & ~out) | self._slave_low)

    async def _run(self) -> None:
        prev = 0x7F
        self.host.set_gpio_in(uio=prev)
        while True:
            await RisingEdge(self.host.dut.clk)
            level = self._wires()
            self.host.set_gpio_in(uio=level)
            self._slave_step(prev, level)
            prev = level

    def _slave_step(self, prev: int, now: int) -> None:
        sda, scl = now & 1, (now >> SCL_PIN) & 1
        psda, pscl = prev & 1, (prev >> SCL_PIN) & 1

        if scl and pscl and psda and not sda:
            self.saw_start = True
            self._bits = []
        if scl and pscl and not psda and sda:
            self.saw_stop = True

        if scl and not pscl:
            self.scl_rises += 1
            if len(self._bits) < 8:
                self._bits.append(sda)

        if pscl and not scl:
            if self._acking:
                self._slave_low &= ~self.SDA
                self._acking = False
            elif len(self._bits) == 8:
                self.bytes.append(int("".join(str(b) for b in self._bits), 2))
                self._bits = []
                self._acking = True
                if self.ack:
                    self._slave_low |= self.SDA


async def start_i2c(dut, *, ack: bool = True) -> tuple[KrakenSerial, I2cBus]:
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    host = KrakenSerial(dut)
    await host.reset()

    words = await host.load_program(HEX_PATH)
    assert len(words) == 15, f"i2c_min.pio should be 15 instructions, got {len(words)}"

    await host.configure_sm(
        0,
        clkdiv=pack_clkdiv(1),
        execctrl=pack_execctrl(
            wrap_bottom=WRAP_BOTTOM,
            wrap_top=len(words) - 1,
            side_pindir=1,  # side-set drives SCL's direction, not its level
        ),
        # OUT MSB first; IN shifts left so the single ACK bit lands in bit 0.
        shiftctrl=pack_shiftctrl(out_shiftdir=0, in_shiftdir=0),
        pinctrl=pack_pinctrl(
            out_base=SDA_PIN,
            out_count=1,
            in_base=SDA_PIN,
            set_base=SDA_PIN,
            set_count=2,  # `set pins, 0` must clear both driven levels
            sideset_base=SCL_PIN,
            sideset_count=1,
        ),
    )

    bus = I2cBus(host, ack=ack)
    bus.start()
    await host.enable(0x1)  # runs `set pins, 0`, then parks on `pull`
    return host, bus


@cocotb.test()
async def test_i2c_byte_is_received_and_acked(dut):
    """A full START / byte / ACK / STOP transfer, decoded by the bus model."""
    address_write = 0x42  # 7-bit address 0x21, write direction
    host, bus = await start_i2c(dut)

    await host.write(TXF0, i2c_word(address_write))
    await ClockCycles(dut.clk, TRANSFER_CYCLES)

    assert bus.saw_start, "no START condition on the bus"
    assert bus.bytes == [address_write], (
        f"slave decoded {[hex(b) for b in bus.bytes]}, expected [0x{address_write:02X}]"
    )
    assert bus.saw_stop, "no STOP condition on the bus"
    # 8 data clocks, the ACK clock, then the SCL release that forms the STOP.
    assert bus.scl_rises == 10, f"expected 10 SCL rising edges, got {bus.scl_rises}"

    ack = await host.read(RXF0)
    assert ack & 1 == 0, f"slave acked, so the sampled bit should be 0, got 0x{ack:08X}"
    bus.stop()


@cocotb.test()
async def test_i2c_nack_is_visible_to_the_host(dut):
    """With no slave pulling SDA down, the master must read back a 1 (NACK)."""
    host, bus = await start_i2c(dut, ack=False)

    await host.write(TXF0, i2c_word(0x42))
    await ClockCycles(dut.clk, TRANSFER_CYCLES)

    ack = await host.read(RXF0)
    assert ack & 1 == 1, f"nobody acked, so the sampled bit should be 1, got 0x{ack:08X}"
    bus.stop()


@cocotb.test()
async def test_i2c_wires_are_only_ever_pulled_low(dut):
    """Open-drain discipline: the master may pull a wire down but never drive it up."""
    host, bus = await start_i2c(dut)

    await host.write(TXF0, i2c_word(0x42))
    await ClockCycles(dut.clk, TRANSFER_CYCLES)

    assert not bus.driven_high, (
        f"master drove SDA/SCL high {len(bus.driven_high)} times, mask {bus.driven_high[0]:#04x}"
    )
    # Both wires must be released once the transfer ends, or the bus stays stuck.
    assert host.gpio_oe() & 0b11 == 0, f"wires not released, oe={host.gpio_oe():#04x}"
    bus.stop()


@cocotb.test()
async def test_i2c_two_transfers_reuse_the_program(dut):
    """The wrap parks on `pull`, so a second byte replays START through STOP."""
    payload = [0x42, 0xA8]
    host, bus = await start_i2c(dut)

    for byte in payload:
        await host.write(TXF0, i2c_word(byte))
        await ClockCycles(dut.clk, TRANSFER_CYCLES)

    assert bus.bytes == payload, (
        f"slave decoded {[hex(b) for b in bus.bytes]}, expected {[hex(b) for b in payload]}"
    )
    assert bus.scl_rises == 20, f"expected 10 SCL rising edges per transfer, got {bus.scl_rises}"
    bus.stop()
