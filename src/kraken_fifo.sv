// Simple synchronous FIFO for PIO TX/RX.
module kraken_fifo
  import kraken_pkg::*;
#(
  parameter int unsigned DEPTH = FIFO_DEPTH
) (
  input  logic  clk,
  input  logic  rst_n,
  input  logic  clear,   // sync clear (SM_RESTART)

  input  logic  push,
  input  data_t push_data,
  output logic  full,

  input  logic  pop,
  output data_t pop_data,
  output logic  empty,

  output logic [$clog2(DEPTH+1)-1:0] level
);
  localparam int unsigned AW = $clog2(DEPTH);

  data_t mem [DEPTH];
  logic [AW-1:0] wr_ptr, rd_ptr;
  logic [$clog2(DEPTH+1)-1:0] count;

  assign full  = (count == DEPTH[$clog2(DEPTH+1)-1:0]);
  assign empty = (count == '0);
  assign level = count;
  assign pop_data = mem[rd_ptr];

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      wr_ptr <= '0;
      rd_ptr <= '0;
      count  <= '0;
      for (int i = 0; i < DEPTH; i++) mem[i] <= '0;
    end else if (clear) begin
      wr_ptr <= '0;
      rd_ptr <= '0;
      count  <= '0;
    end else begin
      unique case ({push && !full, pop && !empty})
        2'b10: begin
          mem[wr_ptr] <= push_data;
          wr_ptr <= wr_ptr + AW'(1);
          count  <= count + 1'b1;
        end
        2'b01: begin
          rd_ptr <= rd_ptr + AW'(1);
          count  <= count - 1'b1;
        end
        2'b11: begin
          mem[wr_ptr] <= push_data;
          wr_ptr <= wr_ptr + AW'(1);
          rd_ptr <= rd_ptr + AW'(1);
        end
        default: ;
      endcase
    end
  end
endmodule
