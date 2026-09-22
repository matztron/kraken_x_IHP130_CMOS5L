// Per-SM clock enable: Pico-style 16.8 fixed-point divider.
// f_sm ≈ f_sys / (INT + FRAC/256); INT==0 means 65536 (FRAC must be 0).
// Phase accumulator in 1/256 units; first-order dither for fractional rates.
module kraken_clkdiv (
  input  logic        clk,
  input  logic        rst_n,
  input  logic        restart,   // pulse: clear phase (CTRL.CLKDIV_RESTART)
  input  logic [31:0] clkdiv,    // INT[31:16], FRAC[15:8], [7:0] unused
  output logic        clk_en
);
  logic [15:0] div_int;
  logic [7:0]  div_frac;
  assign div_int  = clkdiv[31:16];
  assign div_frac = clkdiv[15:8];

  // Divisor in Q16.8 (units of 1/256 sysclk). INT=0 → 65536.0
  logic [31:0] div_q8;
  always_comb begin
    if (div_int == 16'd0)
      div_q8 = 32'h0100_0000; // 65536 << 8
    else
      div_q8 = {8'b0, div_int, div_frac};
  end

  logic [31:0] accum;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      accum  <= '0;
      clk_en <= 1'b1;
    end else if (restart) begin
      accum  <= '0;
      clk_en <= 1'b1;
    end else if (accum + 32'd256 >= div_q8) begin
      accum  <= accum + 32'd256 - div_q8;
      clk_en <= 1'b1;
    end else begin
      accum  <= accum + 32'd256;
      clk_en <= 1'b0;
    end
  end
endmodule
