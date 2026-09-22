// Combinational instruction decode (PIO 16-bit encoding).
module kraken_decode
  import kraken_pkg::*;
(
  input  instr_t   instr,
  output decoded_t dec
);
  always_comb begin
    dec = decode_instr(instr);
  end
endmodule
