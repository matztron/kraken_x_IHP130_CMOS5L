// Program counter register (used by SM control).
module kraken_pc
  import kraken_pkg::*;
(
  input  logic clk,
  input  logic rst_n,
  input  logic load_pc,
  input  pc_t  next_pc,
  output pc_t  pc
);
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) pc <= '0;
    else if (load_pc) pc <= next_pc;
  end
endmodule
