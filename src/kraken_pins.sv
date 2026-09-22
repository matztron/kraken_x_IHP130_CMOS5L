// Pin mapper: SET / OUT / side-set onto GPIO level + OE.
// Side-set wins over SET/OUT on the same pin in the same cycle.
module kraken_pins
  import kraken_pkg::*;
(
  input  logic   clk,
  input  logic   rst_n,
  input  logic   tick,       // SET / OUT (executing, not stalled)
  input  logic   side_tick,  // side-set (first cycle of instr, incl. stalls)

  input  logic [4:0] set_base,
  input  logic [2:0] set_count,
  input  logic [4:0] out_base,
  input  logic [5:0] out_count,
  input  logic [4:0] sideset_base,
  input  logic [2:0] sideset_count,

  input  logic       do_set_pins,
  input  logic       do_set_pindirs,
  input  logic [4:0] set_imm,

  input  logic       do_out_pins,
  input  logic       do_out_pindirs,
  input  data_t      out_data,

  input  logic       do_side,
  input  logic       side_pindir,
  input  logic [4:0] side_imm,

  output gpio_t      gpio_out,
  output gpio_t      gpio_oe
);
  function automatic gpio_t mask_n(logic [5:0] n);
    if (n >= 6'd32) return {GPIO_W{1'b1}};
    return gpio_t'((32'b1 << n) - 32'b1);
  endfunction

  function automatic gpio_t apply_field(
      input gpio_t cur,
      input logic  enable,
      input logic [5:0] count,
      input logic [4:0] base,
      input data_t value
  );
    gpio_t m, v;
    if (!enable || count == 6'd0) return cur;
    m = mask_n(count) << base;
    v = gpio_t'(value) << base;
    return (cur & ~m) | (v & m);
  endfunction

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      gpio_out <= '0;
      gpio_oe  <= '0;
    end else if (tick || side_tick) begin
      gpio_t o, e;
      o = gpio_out;
      e = gpio_oe;
      if (tick) begin
        o = apply_field(o, do_set_pins, {3'b0, set_count}, set_base, data_t'(set_imm));
        o = apply_field(o, do_out_pins, out_count, out_base, out_data);
        e = apply_field(e, do_set_pindirs, {3'b0, set_count}, set_base, data_t'(set_imm));
        e = apply_field(e, do_out_pindirs, out_count, out_base, out_data);
      end
      if (side_tick && do_side) begin
        if (side_pindir)
          e = apply_field(e, 1'b1, {3'b0, sideset_count}, sideset_base, data_t'(side_imm));
        else
          o = apply_field(o, 1'b1, {3'b0, sideset_count}, sideset_base, data_t'(side_imm));
      end
      gpio_out <= o;
      gpio_oe  <= e;
    end
  end
endmodule
