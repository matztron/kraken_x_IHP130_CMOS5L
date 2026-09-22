// PIO block: shared IMEM + IRQ flags + NUM_SM state machines.
module kraken_pio
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

  // Per-SM config (SM s uses slice [W*s +: W])
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

  // Per-SM host FIFOs (SM i uses tx_data[32*i +: 32], etc.)
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
  pc_t    rd_addr [NUM_SM];
  instr_t rd_data [NUM_SM];
  gpio_t  sm_out [NUM_SM];
  gpio_t  sm_oe  [NUM_SM];

  logic [NUM_IRQ-1:0] irq_set_s [NUM_SM];
  logic [NUM_IRQ-1:0] irq_clr_s [NUM_SM];
  logic [NUM_IRQ-1:0] irq_reg;

  assign irq_flags = irq_reg;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) irq_reg <= '0;
    else begin
      logic [NUM_IRQ-1:0] set_m, clr_m;
      set_m = '0;
      clr_m = '0;
      for (int s = 0; s < NUM_SM; s++) begin
        set_m |= irq_set_s[s];
        clr_m |= irq_clr_s[s];
      end
      irq_reg <= (irq_reg | set_m) & ~clr_m;
    end
  end

  kraken_imem #(.NUM_RD(NUM_SM)) u_imem (
    .clk(clk), .rst_n(rst_n),
    .wr_en(imem_wr_en), .wr_addr(imem_wr_addr), .wr_data(imem_wr_data),
    .rd_addr(rd_addr), .rd_data(rd_data)
  );

  for (genvar s = 0; s < NUM_SM; s++) begin : g_sm
    logic [4:0] unused_delay;
    logic unused_exec, unused_stall;
    pc_t pc_s;
    data_t rx_word;
    logic [3:0] tx_lv, rx_lv;

    kraken_sm u_sm (
      .clk(clk), .rst_n(rst_n),
      .enable(sm_enable[s]), .clk_en(clk_en[s]),
      .sm_restart(sm_restart[s]),
      .host_exec_stb(host_exec_stb[s]),
      .host_exec_instr(host_exec_instr[16*s +: 16]),
      .sm_id(2'(s)),
      .wrap_bottom(pc_t'(wrap_bottom[5*s +: 5])),
      .wrap_top(pc_t'(wrap_top[5*s +: 5])),
      .set_base(set_base[5*s +: 5]),
      .set_count(set_count[3*s +: 3]),
      .out_base(out_base[5*s +: 5]),
      .out_count(out_count[6*s +: 6]),
      .in_base(in_base[5*s +: 5]),
      .jmp_pin(jmp_pin[5*s +: 5]),
      .sideset_base(sideset_base[5*s +: 5]),
      .sideset_count(sideset_count[3*s +: 3]),
      .side_en(side_en[s]),
      .side_pindir(side_pindir[s]),
      .in_shiftdir(in_shiftdir[s]),
      .out_shiftdir(out_shiftdir[s]),
      .push_thresh(push_thresh[5*s +: 5]),
      .pull_thresh(pull_thresh[5*s +: 5]),
      .autopush(autopush[s]),
      .autopull(autopull[s]),
      .fjoin_tx(fjoin_tx[s]),
      .fjoin_rx(fjoin_rx[s]),
      .status_sel(status_sel[s]),
      .status_n(status_n[4*s +: 4]),
      .imem_addr(rd_addr[s]), .imem_data(rd_data[s]),
      .gpio_in(gpio_in), .gpio_out(sm_out[s]), .gpio_oe(sm_oe[s]),
      .irq_flags(irq_reg), .irq_set(irq_set_s[s]), .irq_clr(irq_clr_s[s]),
      .tx_push(tx_push[s]), .tx_data(tx_data[32*s +: 32]), .tx_full(tx_full[s]),
      .rx_pop(rx_pop[s]), .rx_data(rx_word), .rx_empty(rx_empty[s]),
      .dbg_pc(pc_s),
      .tx_level_o(tx_lv), .rx_level_o(rx_lv),
      .fdbg_txover(fdbg_txover[s]), .fdbg_txunder(fdbg_txunder[s]),
      .fdbg_rxover(fdbg_rxover[s]), .fdbg_rxunder(fdbg_rxunder[s]),
      .dbg_delay(unused_delay),
      .dbg_executing(unused_exec), .dbg_stalled(unused_stall)
    );
    assign rx_data[32*s +: 32] = rx_word;
    assign sm_pc[5*s +: 5] = pc_s;
    assign tx_level[4*s +: 4] = tx_lv;
    assign rx_level[4*s +: 4] = rx_lv;
  end

  // Highest-numbered SM wins on a given pin (RP2040-style priority)
  always_comb begin
    gpio_out = '0;
    gpio_oe  = '0;
    for (int s = 0; s < NUM_SM; s++) begin
      for (int b = 0; b < GPIO_W; b++) begin
        if (sm_oe[s][b]) begin
          gpio_oe[b]  = 1'b1;
          gpio_out[b] = sm_out[s][b];
        end else if (!gpio_oe[b]) begin
          gpio_out[b] = gpio_out[b] | sm_out[s][b];
        end
      end
    end
  end
endmodule
