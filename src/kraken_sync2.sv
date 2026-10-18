// Two-flop synchronizer for asynchronous pad inputs.
module kraken_sync2 #(
  parameter int unsigned W = 1
) (
  input  logic         clk,
  input  logic         rst_n,
  input  logic [W-1:0] d,
  output logic [W-1:0] q
);
  logic [W-1:0] meta;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      meta <= '0;
      q    <= '0;
    end else begin
      meta <= d;
      q    <= meta;
    end
  end
endmodule
