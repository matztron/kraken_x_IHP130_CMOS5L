// =============================================================================
// kraken_pkg — shared constants, types, and helpers for Kraken IO RTL
// =============================================================================
package kraken_pkg;

  // ---------------------------------------------------------------------------
  // Architecture parameters (defaults; modules may override via #(parameter))
  // ---------------------------------------------------------------------------
  localparam int unsigned INSTR_W        = 16;  // PIO instruction width (pioasm)
  localparam int unsigned DATA_W         = 32;  // ISR / OSR / scratch width
  localparam int unsigned IMEM_DEPTH     = 32;  // shared instruction memory words
  localparam int unsigned PC_W           = $clog2(IMEM_DEPTH);
  localparam int unsigned GPIO_W         = 32;  // GPIO vector width
  localparam int unsigned FIFO_DEPTH     = 4;   // TX/RX FIFO depth per SM
  localparam int unsigned FIFO_JOIN_DEPTH = 8;  // depth when FJOIN merges FIFOs
  localparam int unsigned NUM_SM_DEFAULT = 1;   // default SMs per PIO block
  localparam int unsigned NUM_IRQ        = 8;   // IRQ flags per PIO block

  // EXECCTRL STATUS_SEL: compare TX or RX FIFO level against STATUS_N
  typedef enum logic {
    STATUS_TXLEVEL = 1'b0,
    STATUS_RXLEVEL = 1'b1
  } status_sel_e;

  // Instruction field widths
  localparam int unsigned OPC_W   = 3;
  localparam int unsigned DELAY_W = 5;
  localparam int unsigned ARG1_W  = 3;
  localparam int unsigned ARG2_W  = 5;

  // ---------------------------------------------------------------------------
  // Basic types
  // ---------------------------------------------------------------------------
  typedef logic [INSTR_W-1:0] instr_t;
  typedef logic [DATA_W-1:0]  data_t;
  typedef logic [PC_W-1:0]    pc_t;
  typedef logic [GPIO_W-1:0]  gpio_t;

  // ---------------------------------------------------------------------------
  // Opcode encodings [15:13] — match pioasm / RP2040 PIO
  // ---------------------------------------------------------------------------
  typedef enum logic [OPC_W-1:0] {
    OPC_JMP       = 3'b000,
    OPC_WAIT      = 3'b001,
    OPC_IN        = 3'b010,
    OPC_OUT       = 3'b011,
    OPC_PUSH_PULL = 3'b100,
    OPC_MOV       = 3'b101,
    OPC_IRQ       = 3'b110,
    OPC_SET       = 3'b111
  } opcode_e;

  // SET destination [7:5]
  typedef enum logic [ARG1_W-1:0] {
    SET_DST_PINS    = 3'b000,
    SET_DST_X       = 3'b001,
    SET_DST_Y       = 3'b010,
    SET_DST_PINDIRS = 3'b100
  } set_dst_e;

  // JMP condition [7:5]
  typedef enum logic [ARG1_W-1:0] {
    JMP_ALWAYS = 3'b000,
    JMP_NOT_X  = 3'b001,
    JMP_X_DEC  = 3'b010,
    JMP_NOT_Y  = 3'b011,
    JMP_Y_DEC  = 3'b100,
    JMP_X_NE_Y = 3'b101,
    JMP_PIN    = 3'b110,
    JMP_NOT_OSRE = 3'b111
  } jmp_cond_e;

  // WAIT source [6:5] (polarity is bit7)
  typedef enum logic [1:0] {
    WAIT_GPIO = 2'b00,
    WAIT_PIN  = 2'b01,
    WAIT_IRQ  = 2'b10
  } wait_src_e;

  // IN source / OUT & MOV dest-ish codes [7:5] / [2:0]
  typedef enum logic [2:0] {
    OP_PINS    = 3'b000,
    OP_X       = 3'b001,
    OP_Y       = 3'b010,
    OP_NULL    = 3'b011,
    OP_PINDIRS = 3'b100, // OUT/SET; MOV EXEC uses 100 as dest
    OP_PC_STAT = 3'b101, // OUT PC / MOV PC dest; MOV STATUS src
    OP_ISR     = 3'b110,
    OP_OSR     = 3'b111
  } op_sel_e;

  // MOV operation [4:3]
  typedef enum logic [1:0] {
    MOV_NONE  = 2'b00,
    MOV_INVERT = 2'b01,
    MOV_REVERSE = 2'b10
  } mov_op_e;

  // ALU operations (internal)
  typedef enum logic [1:0] {
    ALU_PASS_A = 2'b00,
    ALU_DEC    = 2'b01,
    ALU_ADD    = 2'b10,
    ALU_SUB    = 2'b11
  } alu_op_e;

  // ---------------------------------------------------------------------------
  // Decoded instruction view
  // ---------------------------------------------------------------------------
  typedef struct packed {
    opcode_e                opcode;
    logic [DELAY_W-1:0]     delay_sideset;
    logic [ARG1_W-1:0]      arg1;
    logic [ARG2_W-1:0]      arg2;
    logic                   is_pull;  // OPC_PUSH_PULL: bit7 distinguishes PULL
    logic                   valid;
  } decoded_t;

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------
  function automatic decoded_t decode_instr(instr_t instr);
    decoded_t d;
    d.opcode        = opcode_e'(instr[15:13]);
    d.delay_sideset = instr[12:8];
    d.arg1          = instr[7:5];
    d.arg2          = instr[4:0];
    d.is_pull       = instr[7];
    d.valid         = 1'b1;
    return d;
  endfunction

  // Delay field with no side-set: bits are delay 0..31.
  function automatic logic [DELAY_W-1:0] delay_from_field(logic [DELAY_W-1:0] field);
    return field;
  endfunction

  // Delay bits remaining after side-set occupies MSBs of [12:8].
  // Mandatory side-set: S data bits; delay width = 5-S.
  // Optional (SIDE_EN): MSB enable + S data bits; delay width = 4-S.
  function automatic logic [DELAY_W-1:0] delay_from_sideset_field(
      input logic [DELAY_W-1:0] field,
      input logic [2:0]         sideset_count,
      input logic               side_en
  );
    logic [2:0] dw;
    if (sideset_count == 3'd0) return field;
    dw = side_en ? 3'(4 - sideset_count) : 3'(5 - sideset_count);
    if (dw == 3'd0) return 5'd0;
    return field & ((5'd1 << dw) - 5'd1);
  endfunction

  function automatic logic side_valid_from_field(
      input logic [DELAY_W-1:0] field,
      input logic [2:0]         sideset_count,
      input logic               side_en
  );
    if (sideset_count == 3'd0) return 1'b0;
    if (side_en) return field[4];
    return 1'b1;
  endfunction

  function automatic logic [4:0] side_data_from_field(
      input logic [DELAY_W-1:0] field,
      input logic [2:0]         sideset_count,
      input logic               side_en
  );
    logic [2:0] s;
    logic [4:0] mask;
    s = sideset_count;
    if (s == 3'd0) return 5'd0;
    mask = (5'd1 << s) - 5'd1;
    if (side_en) return (field >> (4 - s)) & mask;
    return (field >> (5 - s)) & mask;
  endfunction

  // Bit-count field: encoded 0 means 32.
  function automatic logic [5:0] bit_count_decode(logic [ARG2_W-1:0] raw);
    return (raw == '0) ? 6'd32 : {1'b0, raw};
  endfunction

  // Threshold field: 0 means 32.
  function automatic logic [5:0] thresh_decode(logic [4:0] raw);
    return (raw == '0) ? 6'd32 : {1'b0, raw};
  endfunction

  function automatic data_t bit_reverse32(data_t v);
    data_t r;
    for (int i = 0; i < 32; i++) r[i] = v[31-i];
    return r;
  endfunction

  // Shift `n` bits into ISR (right: insert at MSB side; left: at LSB side).
  function automatic data_t isr_shift_in(
      input data_t isr,
      input data_t bits,   // low n bits used
      input logic [5:0] n,
      input logic shift_right
  );
    if (n >= 6'd32) return bits;
    if (shift_right) return (isr >> n) | (bits << (32 - n));
    return (isr << n) | (bits & ((data_t'(1) << n) - 1));
  endfunction

  function automatic data_t osr_take(
      input data_t osr,
      input logic [5:0] n,
      input logic shift_right
  );
    if (n >= 6'd32) return osr;
    if (shift_right) return osr & ((data_t'(1) << n) - 1);
    return osr >> (32 - n);
  endfunction

  function automatic data_t osr_shifted(
      input data_t osr,
      input logic [5:0] n,
      input logic shift_right
  );
    if (n >= 6'd32) return '0;
    if (shift_right) return osr >> n;
    return osr << n;
  endfunction

  // ---------------------------------------------------------------------------
  // AXI-Lite CSR byte addresses (32-bit aligned). Kraken-native map.
  // ---------------------------------------------------------------------------
  localparam logic [31:0] AXIL_ADDR_CTRL      = 32'h0000_0000;
  localparam logic [31:0] AXIL_ADDR_FSTAT     = 32'h0000_0004;
  localparam logic [31:0] AXIL_ADDR_IRQ       = 32'h0000_0008; // R: flags; W1C clear
  localparam logic [31:0] AXIL_ADDR_IRQ_FORCE = 32'h0000_000C; // W: force-set flags
  localparam logic [31:0] AXIL_ADDR_TXF0      = 32'h0000_0010; // W: push SM0 (+ 8*n)
  localparam logic [31:0] AXIL_ADDR_RXF0      = 32'h0000_0014; // R: pop  SM0 (+ 8*n)
  localparam logic [31:0] AXIL_ADDR_IMEM_ADDR = 32'h0000_0020;
  localparam logic [31:0] AXIL_ADDR_IMEM_DATA = 32'h0000_0024; // W16 into IMEM, auto-inc
  localparam logic [31:0] AXIL_ADDR_FDEBUG    = 32'h0000_0028; // sticky FIFO errors, W1C
  localparam logic [31:0] AXIL_ADDR_FLEVEL    = 32'h0000_002C; // TX/RX levels per SM
  // Per-SM config banks: base + 0x20*n + {CLKDIV, EXECCTRL, SHIFTCTRL, PINCTRL, INSTR, ADDR}
  localparam logic [31:0] AXIL_ADDR_SM_BASE   = 32'h0000_0100;
  localparam logic [31:0] AXIL_ADDR_SM_STRIDE = 32'h0000_0020;
  localparam logic [31:0] AXIL_ADDR_CLKDIV    = 32'h0000_0100; // SM0 aliases
  localparam logic [31:0] AXIL_ADDR_EXECCTRL  = 32'h0000_0104;
  localparam logic [31:0] AXIL_ADDR_SHIFTCTRL = 32'h0000_0108;
  localparam logic [31:0] AXIL_ADDR_PINCTRL   = 32'h0000_010C;
  localparam logic [31:0] AXIL_ADDR_SM_INSTR  = 32'h0000_0110; // SM0; forced EXEC
  localparam logic [31:0] AXIL_ADDR_SM_ADDR   = 32'h0000_0114; // SM0; PC readback
  localparam logic [31:0] AXIL_ADDR_ID        = 32'h0000_0FFC; // RO "KRAK"

  localparam logic [31:0] AXIL_ID_VALUE = 32'h4B52_414B; // 'K''R''A''K'

  // CTRL bit fields (Pico-aligned enable/restart; Kraken IRQ IE in [23:16])
  localparam int unsigned AXIL_CTRL_SM_ENABLE_LSB       = 0;
  localparam int unsigned AXIL_CTRL_SM_RESTART_LSB      = 4;
  localparam int unsigned AXIL_CTRL_CLKDIV_RESTART_LSB  = 8;
  localparam int unsigned AXIL_CTRL_IRQ_IE_LSB          = 16;

  // FDEBUG bit fields (Pico-shaped; W1C)
  localparam int unsigned AXIL_FDEBUG_RXSTALL_LSB = 0;   // alias rxover sticky
  localparam int unsigned AXIL_FDEBUG_RXUNDER_LSB = 8;
  localparam int unsigned AXIL_FDEBUG_TXOVER_LSB  = 16;
  localparam int unsigned AXIL_FDEBUG_TXSTALL_LSB = 24;  // alias txunder sticky

  // Pico-compatible CLKDIV pack: INT[31:16], FRAC[15:8]
  function automatic logic [31:0] axil_pack_clkdiv(input logic [15:0] div_int, input logic [7:0] div_frac);
    return {div_int, div_frac, 8'b0};
  endfunction

  function automatic logic [31:0] axil_addr_sm(input int unsigned sm, input logic [31:0] offset);
    return AXIL_ADDR_SM_BASE + (AXIL_ADDR_SM_STRIDE * 32'(sm)) + offset;
  endfunction

  function automatic logic [31:0] axil_addr_clkdiv(input int unsigned sm);
    return axil_addr_sm(sm, 32'h0);
  endfunction

  function automatic logic [31:0] axil_addr_execctrl(input int unsigned sm);
    return axil_addr_sm(sm, 32'h4);
  endfunction

  function automatic logic [31:0] axil_addr_shiftctrl(input int unsigned sm);
    return axil_addr_sm(sm, 32'h8);
  endfunction

  function automatic logic [31:0] axil_addr_pinctrl(input int unsigned sm);
    return axil_addr_sm(sm, 32'hC);
  endfunction

  function automatic logic [31:0] axil_addr_sm_instr(input int unsigned sm);
    return axil_addr_sm(sm, 32'h10);
  endfunction

  function automatic logic [31:0] axil_addr_sm_addr(input int unsigned sm);
    return axil_addr_sm(sm, 32'h14);
  endfunction

endpackage
