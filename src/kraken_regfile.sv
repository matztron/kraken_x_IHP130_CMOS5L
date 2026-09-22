// Scratch + shift registers for one state machine.
module kraken_regfile
  import kraken_pkg::*;
(
  input  logic   clk,
  input  logic   rst_n,
  input  logic   clear,      // SM_RESTART
  input  logic   tick,       // SM enabled and executing (not in delay)

  input  logic   we_x,
  input  logic   we_y,
  input  logic   we_isr,
  input  logic   we_osr,
  input  data_t  wdata_x,
  input  data_t  wdata_y,
  input  data_t  wdata_isr,
  input  data_t  wdata_osr,

  output data_t  x,
  output data_t  y,
  output data_t  isr,
  output data_t  osr
);
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n || clear) begin
      x   <= '0;
      y   <= '0;
      isr <= '0;
      osr <= '0;
    end else if (tick) begin
      if (we_x)   x   <= wdata_x;
      if (we_y)   y   <= wdata_y;
      if (we_isr) isr <= wdata_isr;
      if (we_osr) osr <= wdata_osr;
    end
  end
endmodule
