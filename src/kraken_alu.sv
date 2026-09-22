// Small ALU for scratch ops (X--, compares later) and immediate expand.
module kraken_alu
  import kraken_pkg::*;
(
  input  alu_op_e op,
  input  data_t   a,
  input  data_t   b,
  output data_t   y,
  output logic    z   // result == 0
);
  always_comb begin
    unique case (op)
      ALU_PASS_A: y = a;
      ALU_DEC:    y = a - data_t'(1);
      ALU_ADD:    y = a + b;
      ALU_SUB:    y = a - b;
      default:    y = a;
    endcase
    z = (y == '0);
  end
endmodule
