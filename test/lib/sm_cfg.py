# Shared helpers for packed per-SM flat ports on kraken_io.


def bcast(val: int, width: int, num_sm: int) -> int:
    """Replicate a field value across NUM_SM packed slices."""
    mask = (1 << width) - 1
    out = 0
    for i in range(num_sm):
        out |= (val & mask) << (width * i)
    return out


def pack_execctrl(
    *,
    wrap_bottom: int = 0,
    wrap_top: int = 0x1F,
    jmp_pin: int = 0,
    status_sel: int = 0,
    status_n: int = 0,
    side_en: int = 0,
    side_pindir: int = 0,
) -> int:
    return (
        (wrap_bottom & 0x1F)
        | ((wrap_top & 0x1F) << 5)
        | ((jmp_pin & 0x1F) << 10)
        | ((status_sel & 1) << 15)
        | ((status_n & 0xF) << 16)
        | ((side_en & 1) << 20)
        | ((side_pindir & 1) << 21)
    )


def pack_shiftctrl(
    *,
    in_shiftdir: int = 0,
    out_shiftdir: int = 1,
    autopush: int = 0,
    autopull: int = 0,
    fjoin_tx: int = 0,
    fjoin_rx: int = 0,
    push_thresh: int = 0,
    pull_thresh: int = 0,
) -> int:
    return (
        (in_shiftdir & 1)
        | ((out_shiftdir & 1) << 1)
        | ((autopush & 1) << 2)
        | ((autopull & 1) << 3)
        | ((fjoin_tx & 1) << 4)
        | ((fjoin_rx & 1) << 5)
        | ((push_thresh & 0x1F) << 8)
        | ((pull_thresh & 0x1F) << 13)
    )


def pack_pinctrl(
    *,
    out_base: int = 0,
    out_count: int = 0,
    set_base: int = 0,
    set_count: int = 0,
    sideset_base: int = 0,
    sideset_count: int = 0,
    in_base: int = 0,
) -> int:
    return (
        (out_base & 0x1F)
        | ((out_count & 0x3F) << 5)
        | ((set_base & 0x1F) << 11)
        | ((set_count & 0x7) << 16)
        | ((sideset_base & 0x1F) << 19)
        | ((sideset_count & 0x7) << 24)
        | ((in_base & 0x1F) << 27)
    )


def pack_clkdiv(div_int: int, div_frac: int = 0) -> int:
    return ((div_int & 0xFFFF) << 16) | ((div_frac & 0xFF) << 8)


def sm_addr(sm: int, offset: int) -> int:
    """AXI SM bank: 0x100 + 0x20*sm + offset (0=CLKDIV, 4=EXEC, 8=SHIFT, C=PIN)."""
    return 0x100 + 0x20 * sm + offset
