// Kraken IO top-level IP (flat ports; config is per-SM packed).
module kraken_io
  import kraken_pkg::*;
#(
  parameter int unsigned NUM_SM = NUM_SM_DEFAULT
) (
  input  logic clk,
  input  logic rst_n,

  input  logic   imem_wr_en,
  input  pc_t    imem_wr_addr,
  input  instr_t imem_wr_data,

  input  logic [NUM_SM-1:0] sm_enable,
  input  logic [NUM_SM-1:0] clk_en,
  input  logic [NUM_SM-1:0] sm_restart,
  input  logic [NUM_SM-1:0] host_exec_stb,
  input  logic [16*NUM_SM-1:0] host_exec_instr,

  input  logic [5*NUM_SM-1:0] wrap_bottom,
  input  logic [5*NUM_SM-1:0] wrap_top,
  input  logic [5*NUM_SM-1:0] set_base,
  input  logic [3*NUM_SM-1:0] set_count,
  input  logic [5*NUM_SM-1:0] out_base,
  input  logic [6*NUM_SM-1:0] out_count,
  input  logic [5*NUM_SM-1:0] in_base,
  input  logic [5*NUM_SM-1:0] jmp_pin,

  input  logic [5*NUM_SM-1:0] sideset_base,
  input  logic [3*NUM_SM-1:0] sideset_count,
  input  logic [NUM_SM-1:0]   side_en,
  input  logic [NUM_SM-1:0]   side_pindir,

  input  logic [NUM_SM-1:0]   in_shiftdir,
  input  logic [NUM_SM-1:0]   out_shiftdir,
  input  logic [5*NUM_SM-1:0] push_thresh,
  input  logic [5*NUM_SM-1:0] pull_thresh,
  input  logic [NUM_SM-1:0]   autopush,
  input  logic [NUM_SM-1:0]   autopull,
  input  logic [NUM_SM-1:0]   fjoin_tx,
  input  logic [NUM_SM-1:0]   fjoin_rx,

  input  logic [NUM_SM-1:0]   status_sel,
  input  logic [4*NUM_SM-1:0] status_n,

  input  gpio_t gpio_in,
  output gpio_t gpio_out,
  output gpio_t gpio_oe,

  input  logic [NUM_SM-1:0]        tx_push,
  input  logic [32*NUM_SM-1:0]     tx_data,
  output logic [NUM_SM-1:0]        tx_full,
  input  logic [NUM_SM-1:0]        rx_pop,
  output logic [32*NUM_SM-1:0]     rx_data,
  output logic [NUM_SM-1:0]        rx_empty,

  output logic [5*NUM_SM-1:0]      sm_pc,
  output logic [4*NUM_SM-1:0]      tx_level,
  output logic [4*NUM_SM-1:0]      rx_level,
  output logic [NUM_SM-1:0]        fdbg_txover,
  output logic [NUM_SM-1:0]        fdbg_txunder,
  output logic [NUM_SM-1:0]        fdbg_rxover,
  output logic [NUM_SM-1:0]        fdbg_rxunder,

  output logic [NUM_IRQ-1:0] irq_flags
);
  kraken_pio #(.NUM_SM(NUM_SM)) u_pio (.*);
endmodule
