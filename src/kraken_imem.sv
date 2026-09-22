// Shared instruction memory: 1 write port, NUM_RD read ports.
module kraken_imem
  import kraken_pkg::*;
#(
  parameter int unsigned NUM_RD = 1
) (
  input  logic                  clk,
  input  logic                  rst_n,

  // Host program load
  input  logic                  wr_en,
  input  pc_t                   wr_addr,
  input  instr_t                wr_data,

  // State-machine fetches
  input  pc_t                   rd_addr [NUM_RD],
  output instr_t                rd_data [NUM_RD]
);
  instr_t mem [IMEM_DEPTH];

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      for (int i = 0; i < IMEM_DEPTH; i++) begin
        mem[i] <= '0;
      end
    end else if (wr_en) begin
      mem[wr_addr] <= wr_data;
    end
  end

  always_comb begin
    for (int r = 0; r < NUM_RD; r++) begin
      rd_data[r] = mem[rd_addr[r]];
    end
  end
endmodule
