// AXI4-Lite slave + CSR bridge for kraken_io (Kraken-native register map).
module kraken_axil
  import kraken_pkg::*;
#(
  parameter int unsigned NUM_SM = NUM_SM_DEFAULT,
  parameter int unsigned ADDR_W = 12
) (
  input  logic clk,
  input  logic rst_n,

  input  logic [ADDR_W-1:0] s_axil_awaddr,
  input  logic              s_axil_awvalid,
  output logic              s_axil_awready,
  input  logic [31:0]       s_axil_wdata,
  input  logic [3:0]        s_axil_wstrb,
  input  logic              s_axil_wvalid,
  output logic              s_axil_wready,
  output logic [1:0]        s_axil_bresp,
  output logic              s_axil_bvalid,
  input  logic              s_axil_bready,
  input  logic [ADDR_W-1:0] s_axil_araddr,
  input  logic              s_axil_arvalid,
  output logic              s_axil_arready,
  output logic [31:0]       s_axil_rdata,
  output logic [1:0]        s_axil_rresp,
  output logic              s_axil_rvalid,
  input  logic              s_axil_rready,

  input  gpio_t gpio_in,
  output gpio_t gpio_out,
  output gpio_t gpio_oe,
  output logic  irq
);
  // ---- CSRs ----
  logic [NUM_SM-1:0] ctrl_enable;
  logic [7:0]        irq_ie;
  logic [31:0]       clkdiv_reg [NUM_SM];
  logic [NUM_SM-1:0] clkdiv_restart;
  logic [NUM_SM-1:0] sm_restart;
  logic [NUM_SM-1:0] host_exec_stb;
  logic [16*NUM_SM-1:0] host_exec_instr;
  logic [31:0]       execctrl  [NUM_SM];
  logic [31:0]       shiftctrl [NUM_SM];
  logic [31:0]       pinctrl   [NUM_SM];
  logic [4:0]        imem_addr_r;
  logic [NUM_IRQ-1:0] irq_force_sticky;
  logic [NUM_SM-1:0] fdbg_rxstall_r, fdbg_rxunder_r, fdbg_txover_r, fdbg_txstall_r;
  data_t             tx_hold [NUM_SM];
  instr_t            sm_instr_hold [NUM_SM];

  logic        imem_wr_en;
  pc_t         imem_wr_addr;
  instr_t      imem_wr_data;
  logic [NUM_SM-1:0] tx_push, rx_pop;

  logic [5*NUM_SM-1:0] wrap_bottom, wrap_top, set_base, out_base, in_base, jmp_pin;
  logic [5*NUM_SM-1:0] sideset_base, push_thresh, pull_thresh;
  logic [3*NUM_SM-1:0] set_count, sideset_count;
  logic [6*NUM_SM-1:0] out_count;
  logic [NUM_SM-1:0]   status_sel, side_en, side_pindir;
  logic [NUM_SM-1:0]   in_shiftdir, out_shiftdir, autopush, autopull, fjoin_tx, fjoin_rx;
  logic [4*NUM_SM-1:0] status_n;

  always_comb begin
    wrap_bottom = '0;
    wrap_top = '0;
    jmp_pin = '0;
    status_sel = '0;
    status_n = '0;
    side_en = '0;
    side_pindir = '0;
    in_shiftdir = '0;
    out_shiftdir = '0;
    autopush = '0;
    autopull = '0;
    fjoin_tx = '0;
    fjoin_rx = '0;
    push_thresh = '0;
    pull_thresh = '0;
    out_base = '0;
    out_count = '0;
    set_base = '0;
    set_count = '0;
    sideset_base = '0;
    sideset_count = '0;
    in_base = '0;
    for (int s = 0; s < NUM_SM; s++) begin
      wrap_bottom[5*s +: 5]  = execctrl[s][4:0];
      wrap_top[5*s +: 5]     = execctrl[s][9:5];
      jmp_pin[5*s +: 5]      = execctrl[s][14:10];
      status_sel[s]          = execctrl[s][15];
      status_n[4*s +: 4]     = execctrl[s][19:16];
      side_en[s]             = execctrl[s][20];
      side_pindir[s]         = execctrl[s][21];
      in_shiftdir[s]         = shiftctrl[s][0];
      out_shiftdir[s]        = shiftctrl[s][1];
      autopush[s]            = shiftctrl[s][2];
      autopull[s]            = shiftctrl[s][3];
      fjoin_tx[s]            = shiftctrl[s][4];
      fjoin_rx[s]            = shiftctrl[s][5];
      push_thresh[5*s +: 5]  = shiftctrl[s][12:8];
      pull_thresh[5*s +: 5]  = shiftctrl[s][17:13];
      out_base[5*s +: 5]     = pinctrl[s][4:0];
      out_count[6*s +: 6]    = pinctrl[s][10:5];
      set_base[5*s +: 5]     = pinctrl[s][15:11];
      set_count[3*s +: 3]    = pinctrl[s][18:16];
      sideset_base[5*s +: 5] = pinctrl[s][23:19];
      sideset_count[3*s +: 3]= pinctrl[s][26:24];
      in_base[5*s +: 5]      = pinctrl[s][31:27];
    end
  end

  logic [NUM_SM-1:0] clk_en;
  for (genvar gs = 0; gs < NUM_SM; gs++) begin : g_clkdiv
    kraken_clkdiv u_clkdiv (
      .clk(clk),
      .rst_n(rst_n),
      .restart(clkdiv_restart[gs]),
      .clkdiv(clkdiv_reg[gs]),
      .clk_en(clk_en[gs])
    );
  end

  logic [NUM_SM-1:0] tx_full, rx_empty;
  logic [32*NUM_SM-1:0] tx_data_bus, rx_data_bus;
  logic [NUM_IRQ-1:0] irq_flags;
  logic [5*NUM_SM-1:0] sm_pc_bus;
  logic [4*NUM_SM-1:0] tx_level_bus, rx_level_bus;
  logic [NUM_SM-1:0] fdbg_txover, fdbg_txunder, fdbg_rxover, fdbg_rxunder;

  always_comb begin
    tx_data_bus = '0;
    for (int s = 0; s < NUM_SM; s++) tx_data_bus[32*s +: 32] = tx_hold[s];
  end

  kraken_io #(.NUM_SM(NUM_SM)) u_io (
    .clk(clk), .rst_n(rst_n),
    .imem_wr_en(imem_wr_en), .imem_wr_addr(imem_wr_addr), .imem_wr_data(imem_wr_data),
    .sm_enable(ctrl_enable), .clk_en(clk_en),
    .sm_restart(sm_restart),
    .host_exec_stb(host_exec_stb),
    .host_exec_instr(host_exec_instr),
    .wrap_bottom(wrap_bottom), .wrap_top(wrap_top),
    .set_base(set_base), .set_count(set_count),
    .out_base(out_base), .out_count(out_count),
    .in_base(in_base), .jmp_pin(jmp_pin),
    .sideset_base(sideset_base), .sideset_count(sideset_count),
    .side_en(side_en), .side_pindir(side_pindir),
    .in_shiftdir(in_shiftdir), .out_shiftdir(out_shiftdir),
    .push_thresh(push_thresh), .pull_thresh(pull_thresh),
    .autopush(autopush), .autopull(autopull),
    .fjoin_tx(fjoin_tx), .fjoin_rx(fjoin_rx),
    .status_sel(status_sel), .status_n(status_n),
    .gpio_in(gpio_in), .gpio_out(gpio_out), .gpio_oe(gpio_oe),
    .tx_push(tx_push), .tx_data(tx_data_bus), .tx_full(tx_full),
    .rx_pop(rx_pop), .rx_data(rx_data_bus), .rx_empty(rx_empty),
    .sm_pc(sm_pc_bus), .tx_level(tx_level_bus), .rx_level(rx_level_bus),
    .fdbg_txover(fdbg_txover), .fdbg_txunder(fdbg_txunder),
    .fdbg_rxover(fdbg_rxover), .fdbg_rxunder(fdbg_rxunder),
    .irq_flags(irq_flags)
  );

  logic [NUM_IRQ-1:0] irq_visible;
  assign irq_visible = irq_flags | irq_force_sticky;
  assign irq = |(irq_visible & irq_ie[NUM_IRQ-1:0]);

  // ---- AXI helpers ----
  function automatic logic [31:0] merge_wstrb(
      input logic [31:0] prev, input logic [31:0] wdata, input logic [3:0] wstrb
  );
    logic [31:0] r = prev;
    if (wstrb[0]) r[7:0]   = wdata[7:0];
    if (wstrb[1]) r[15:8]  = wdata[15:8];
    if (wstrb[2]) r[23:16] = wdata[23:16];
    if (wstrb[3]) r[31:24] = wdata[31:24];
    return r;
  endfunction

  function automatic logic [31:0] a32(input logic [ADDR_W-1:0] a);
    return {{(32-ADDR_W){1'b0}}, a} & 32'h0000_0FFC;
  endfunction

  logic [31:0] fstat_word, fdebug_word, flevel_word, ctrl_rd;
  always_comb begin
    fstat_word = '0;
    fdebug_word = '0;
    flevel_word = '0;
    for (int s = 0; s < NUM_SM; s++) begin
      fstat_word[s]     = tx_full[s];
      fstat_word[8 + s] = rx_empty[s];
      fdebug_word[AXIL_FDEBUG_RXSTALL_LSB + s] = fdbg_rxstall_r[s];
      fdebug_word[AXIL_FDEBUG_RXUNDER_LSB + s] = fdbg_rxunder_r[s];
      fdebug_word[AXIL_FDEBUG_TXOVER_LSB  + s] = fdbg_txover_r[s];
      fdebug_word[AXIL_FDEBUG_TXSTALL_LSB + s] = fdbg_txstall_r[s];
      // Pico FLEVEL: TX in low nibble of byte s, RX in high nibble
      flevel_word[8*s +: 4]     = tx_level_bus[4*s +: 4];
      flevel_word[8*s + 4 +: 4] = rx_level_bus[4*s +: 4];
    end
    ctrl_rd = '0;
    ctrl_rd[NUM_SM-1:0] = ctrl_enable;
    // SM_RESTART / CLKDIV_RESTART are SC — reads as 0
    ctrl_rd[AXIL_CTRL_IRQ_IE_LSB +: 8] = irq_ie;
  end

  // Captured write/read request
  logic              wr_valid, rd_valid, wr_done, rd_done;
  logic [ADDR_W-1:0] wr_addr, rd_addr;
  logic [31:0]       wr_data, rd_data;
  logic [3:0]        wr_strb;

  logic have_aw, have_w;

  assign s_axil_bresp = 2'b00;
  assign s_axil_rresp = 2'b00;
  assign s_axil_rdata = rd_data;

  // AW / W capture (skid until both present and not busy)
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      have_aw <= 1'b0;
      have_w  <= 1'b0;
      wr_addr <= '0;
      wr_data <= '0;
      wr_strb <= '0;
      s_axil_awready <= 1'b1;
      s_axil_wready  <= 1'b1;
      s_axil_bvalid  <= 1'b0;
      wr_valid <= 1'b0;
    end else begin
      // Complete write response
      if (s_axil_bvalid && s_axil_bready) s_axil_bvalid <= 1'b0;

      // Accept new AW/W when not holding a pending pair / response
      if (!have_aw && !(wr_valid || s_axil_bvalid)) begin
        s_axil_awready <= 1'b1;
        if (s_axil_awvalid && s_axil_awready) begin
          wr_addr <= s_axil_awaddr;
          have_aw <= 1'b1;
          s_axil_awready <= 1'b0;
        end
      end else s_axil_awready <= 1'b0;

      if (!have_w && !(wr_valid || s_axil_bvalid)) begin
        s_axil_wready <= 1'b1;
        if (s_axil_wvalid && s_axil_wready) begin
          wr_data <= s_axil_wdata;
          wr_strb <= s_axil_wstrb;
          have_w  <= 1'b1;
          s_axil_wready <= 1'b0;
        end
      end else s_axil_wready <= 1'b0;

      // Fire write when both halves captured
      if (have_aw && have_w && !wr_valid && !s_axil_bvalid) begin
        wr_valid <= 1'b1;
        have_aw  <= 1'b0;
        have_w   <= 1'b0;
      end else if (wr_done) begin
        wr_valid <= 1'b0;
        s_axil_bvalid <= 1'b1;
      end
    end
  end

  // AR capture / R response
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      s_axil_arready <= 1'b1;
      s_axil_rvalid  <= 1'b0;
      rd_addr  <= '0;
      rd_data  <= '0;
      rd_valid <= 1'b0;
    end else begin
      if (s_axil_rvalid && s_axil_rready) s_axil_rvalid <= 1'b0;

      if (!rd_valid && !s_axil_rvalid) begin
        s_axil_arready <= 1'b1;
        if (s_axil_arvalid && s_axil_arready) begin
          rd_addr <= s_axil_araddr;
          rd_valid <= 1'b1;
          s_axil_arready <= 1'b0;
        end
      end else s_axil_arready <= 1'b0;

      if (rd_done) begin
        rd_valid <= 1'b0;
        s_axil_rvalid <= 1'b1;
      end
    end
  end

  // Register file + side effects (combinational done pulses via regs)
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      ctrl_enable <= '0;
      irq_ie <= '0;
      clkdiv_restart <= '0;
      sm_restart <= '0;
      host_exec_stb <= '0;
      host_exec_instr <= '0;
      imem_addr_r <= '0;
      irq_force_sticky <= '0;
      fdbg_rxstall_r <= '0;
      fdbg_rxunder_r <= '0;
      fdbg_txover_r <= '0;
      fdbg_txstall_r <= '0;
      imem_wr_en <= 1'b0;
      imem_wr_addr <= '0;
      imem_wr_data <= '0;
      tx_push <= '0;
      rx_pop  <= '0;
      wr_done <= 1'b0;
      rd_done <= 1'b0;
      for (int s = 0; s < NUM_SM; s++) begin
        tx_hold[s]      <= '0;
        sm_instr_hold[s]<= '0;
        clkdiv_reg[s]   <= axil_pack_clkdiv(16'd1, 8'd0);
        execctrl[s]     <= 32'h0000_003E;
        shiftctrl[s]    <= 32'h0000_0003;
        pinctrl[s]      <= 32'h0000_0020;
      end
    end else begin
      imem_wr_en <= 1'b0;
      tx_push    <= '0;
      rx_pop     <= '0;
      wr_done    <= 1'b0;
      rd_done    <= 1'b0;
      clkdiv_restart <= '0; // SC pulses
      sm_restart     <= '0;
      host_exec_stb  <= '0;

      begin
        logic [NUM_SM-1:0] rxstall_n, rxunder_n, txover_n, txstall_n;
        rxstall_n = fdbg_rxstall_r | fdbg_rxover;
        rxunder_n = fdbg_rxunder_r | fdbg_rxunder;
        txover_n  = fdbg_txover_r  | fdbg_txover;
        txstall_n = fdbg_txstall_r | fdbg_txunder;

        if (wr_valid && !wr_done && a32(wr_addr) == AXIL_ADDR_FDEBUG) begin
          rxstall_n = rxstall_n & ~wr_data[AXIL_FDEBUG_RXSTALL_LSB +: NUM_SM];
          rxunder_n = rxunder_n & ~wr_data[AXIL_FDEBUG_RXUNDER_LSB +: NUM_SM];
          txover_n  = txover_n  & ~wr_data[AXIL_FDEBUG_TXOVER_LSB  +: NUM_SM];
          txstall_n = txstall_n & ~wr_data[AXIL_FDEBUG_TXSTALL_LSB +: NUM_SM];
        end
        // Host RXUNDER on empty RXF read
        if (rd_valid && !rd_done) begin
          for (int s = 0; s < NUM_SM; s++)
            if (a32(rd_addr) == (AXIL_ADDR_RXF0 + (32'(s) << 3)) && rx_empty[s])
              rxunder_n[s] = 1'b1;
        end
        fdbg_rxstall_r <= rxstall_n;
        fdbg_rxunder_r <= rxunder_n;
        fdbg_txover_r  <= txover_n;
        fdbg_txstall_r <= txstall_n;
      end

      if (wr_valid && !wr_done) begin
        unique case (a32(wr_addr))
          AXIL_ADDR_CTRL: begin
            logic [31:0] v;
            v = merge_wstrb(ctrl_rd, wr_data, wr_strb);
            ctrl_enable    <= v[NUM_SM-1:0];
            irq_ie         <= v[AXIL_CTRL_IRQ_IE_LSB +: 8];
            sm_restart     <= v[AXIL_CTRL_SM_RESTART_LSB +: NUM_SM];
            clkdiv_restart <= v[AXIL_CTRL_CLKDIV_RESTART_LSB +: NUM_SM];
          end
          AXIL_ADDR_IRQ:
            irq_force_sticky <= irq_force_sticky & ~wr_data[NUM_IRQ-1:0];
          AXIL_ADDR_IRQ_FORCE:
            irq_force_sticky <= irq_force_sticky | wr_data[NUM_IRQ-1:0];
          AXIL_ADDR_IMEM_ADDR:
            imem_addr_r <= merge_wstrb({27'b0, imem_addr_r}, wr_data, wr_strb)[4:0];
          AXIL_ADDR_IMEM_DATA: begin
            imem_wr_en   <= 1'b1;
            imem_wr_addr <= imem_addr_r;
            imem_wr_data <= merge_wstrb('0, wr_data, wr_strb)[15:0];
            imem_addr_r  <= imem_addr_r + 5'd1;
          end
          AXIL_ADDR_FDEBUG: ; // sticky clear handled above
          default: begin
            for (int s = 0; s < NUM_SM; s++) begin
              if (a32(wr_addr) == axil_addr_clkdiv(s))
                clkdiv_reg[s] <= merge_wstrb(clkdiv_reg[s], wr_data, wr_strb) & 32'hFFFF_FF00;
              if (a32(wr_addr) == axil_addr_execctrl(s))
                execctrl[s] <= merge_wstrb(execctrl[s], wr_data, wr_strb);
              if (a32(wr_addr) == axil_addr_shiftctrl(s))
                shiftctrl[s] <= merge_wstrb(shiftctrl[s], wr_data, wr_strb);
              if (a32(wr_addr) == axil_addr_pinctrl(s))
                pinctrl[s] <= merge_wstrb(pinctrl[s], wr_data, wr_strb);
              if (a32(wr_addr) == axil_addr_sm_instr(s)) begin
                sm_instr_hold[s] <= merge_wstrb({16'b0, sm_instr_hold[s]}, wr_data, wr_strb)[15:0];
                host_exec_instr[16*s +: 16] <= merge_wstrb({16'b0, sm_instr_hold[s]}, wr_data, wr_strb)[15:0];
                host_exec_stb[s] <= 1'b1;
              end
              if (a32(wr_addr) == (AXIL_ADDR_TXF0 + (32'(s) << 3))) begin
                tx_hold[s] <= merge_wstrb(tx_hold[s], wr_data, wr_strb);
                tx_push[s] <= 1'b1;
              end
            end
          end
        endcase
        wr_done <= 1'b1;
      end

      if (rd_valid && !rd_done) begin
        unique case (a32(rd_addr))
          AXIL_ADDR_CTRL:      rd_data <= ctrl_rd;
          AXIL_ADDR_FSTAT:     rd_data <= fstat_word;
          AXIL_ADDR_IRQ:       rd_data <= {24'b0, irq_visible};
          AXIL_ADDR_IRQ_FORCE: rd_data <= {24'b0, irq_force_sticky};
          AXIL_ADDR_IMEM_ADDR: rd_data <= {27'b0, imem_addr_r};
          AXIL_ADDR_IMEM_DATA: rd_data <= 32'h0;
          AXIL_ADDR_FDEBUG:    rd_data <= fdebug_word;
          AXIL_ADDR_FLEVEL:    rd_data <= flevel_word;
          AXIL_ADDR_ID:        rd_data <= AXIL_ID_VALUE;
          default: begin
            rd_data <= 32'hDEAD_BEEF;
            for (int s = 0; s < NUM_SM; s++) begin
              if (a32(rd_addr) == axil_addr_clkdiv(s))
                rd_data <= clkdiv_reg[s] & 32'hFFFF_FF00;
              if (a32(rd_addr) == axil_addr_execctrl(s))
                rd_data <= execctrl[s];
              if (a32(rd_addr) == axil_addr_shiftctrl(s))
                rd_data <= shiftctrl[s];
              if (a32(rd_addr) == axil_addr_pinctrl(s))
                rd_data <= pinctrl[s];
              if (a32(rd_addr) == axil_addr_sm_instr(s))
                rd_data <= {16'b0, sm_instr_hold[s]};
              if (a32(rd_addr) == axil_addr_sm_addr(s))
                rd_data <= {27'b0, sm_pc_bus[5*s +: 5]};
              if (a32(rd_addr) == (AXIL_ADDR_RXF0 + (32'(s) << 3))) begin
                rd_data <= rx_data_bus[32*s +: 32];
                if (!rx_empty[s]) rx_pop[s] <= 1'b1;
              end
              if (a32(rd_addr) == (AXIL_ADDR_TXF0 + (32'(s) << 3)))
                rd_data <= tx_hold[s];
            end
          end
        endcase
        rd_done <= 1'b1;
      end
    end
  end
endmodule
