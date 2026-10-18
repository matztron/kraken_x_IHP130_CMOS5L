// TinyTapeout pad wiring for one kraken_axil block.
//
// Host link (see kraken_serial_host for the frame format):
//   ui_in[7]     SCK
//   uio[7]       SDIO, bidirectional
//
// Protocol pins, 22 in total:
//   uio[6:0]     gpio[6:0]    bidirectional, driven with gpio_oe
//   uo_out[7:0]  gpio[14:7]   output only
//   ui_in[6:0]   gpio[21:15]  input only
//
// Output-only pads read back the level Kraken drives, so WAIT PIN and IN PINS
// on gpio[14:7] see the driven value. gpio[31:22] is not bonded out and reads 0.
module kraken_tt_host
  import kraken_pkg::*;
#(
  parameter int unsigned NUM_SM = NUM_SM_DEFAULT
) (
  input  logic       clk,
  input  logic       rst_n,
  input  logic       ena,
  input  logic [7:0] ui_in,
  output logic [7:0] uo_out,
  input  logic [7:0] uio_in,
  output logic [7:0] uio_out,
  output logic [7:0] uio_oe
);
  typedef enum logic [2:0] {
    ST_IDLE,
    ST_AW,
    ST_B,
    ST_AR,
    ST_R
  } state_e;

  state_e state;
  logic   aw_done, w_done;

  logic        req_stb, req_write;
  logic [11:0] req_addr;
  logic [31:0] req_wdata;
  logic [31:0] rbuf;

  logic sdio_out, sdio_oe;

  logic [11:0] axil_awaddr, axil_araddr;
  logic        axil_awvalid, axil_awready;
  logic [31:0] axil_wdata;
  logic        axil_wvalid, axil_wready;
  logic [1:0]  axil_bresp;
  logic        axil_bvalid;
  logic        axil_arvalid, axil_arready;
  logic [31:0] axil_rdata;
  logic [1:0]  axil_rresp;
  logic        axil_rvalid;

  gpio_t gpio_in, gpio_out, gpio_oe;
  logic  irq;

  logic [6:0] uio_in_s, ui_in_s;

  kraken_serial_host u_link (
    .clk(clk),
    .rst_n(rst_n),
    .sck_pad(ui_in[7]),
    .sdio_pad(uio_in[7]),
    .sdio_out(sdio_out),
    .sdio_oe(sdio_oe),
    .req_stb(req_stb),
    .req_write(req_write),
    .req_addr(req_addr),
    .req_wdata(req_wdata),
    .rsp_data(rbuf)
  );

  kraken_sync2 #(.W(7)) u_sync_uio (.clk(clk), .rst_n(rst_n), .d(uio_in[6:0]), .q(uio_in_s));
  kraken_sync2 #(.W(7)) u_sync_ui  (.clk(clk), .rst_n(rst_n), .d(ui_in[6:0]),  .q(ui_in_s));

  assign gpio_in = {10'b0, ui_in_s, gpio_out[14:7], uio_in_s};

  assign uio_out = {sdio_out, gpio_out[6:0]};
  assign uio_oe  = {sdio_oe, gpio_oe[6:0]};
  assign uo_out  = ena ? gpio_out[14:7] : 8'b0;

  wire _unused = &{axil_bresp, axil_rresp, gpio_oe[31:7], gpio_out[31:15], irq, 1'b0};

  kraken_axil #(.NUM_SM(NUM_SM)) u_kraken (
    .clk(clk),
    .rst_n(rst_n),
    .s_axil_awaddr(axil_awaddr),
    .s_axil_awvalid(axil_awvalid),
    .s_axil_awready(axil_awready),
    .s_axil_wdata(axil_wdata),
    .s_axil_wstrb(4'b1111),
    .s_axil_wvalid(axil_wvalid),
    .s_axil_wready(axil_wready),
    .s_axil_bresp(axil_bresp),
    .s_axil_bvalid(axil_bvalid),
    .s_axil_bready(1'b1),
    .s_axil_araddr(axil_araddr),
    .s_axil_arvalid(axil_arvalid),
    .s_axil_arready(axil_arready),
    .s_axil_rdata(axil_rdata),
    .s_axil_rresp(axil_rresp),
    .s_axil_rvalid(axil_rvalid),
    .s_axil_rready(1'b1),
    .gpio_in(gpio_in),
    .gpio_out(gpio_out),
    .gpio_oe(gpio_oe),
    .irq(irq)
  );

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state        <= ST_IDLE;
      aw_done      <= 1'b0;
      w_done       <= 1'b0;
      rbuf         <= '0;
      axil_awaddr  <= '0;
      axil_awvalid <= 1'b0;
      axil_wdata   <= '0;
      axil_wvalid  <= 1'b0;
      axil_araddr  <= '0;
      axil_arvalid <= 1'b0;
    end else begin
      unique case (state)
        ST_IDLE: begin
          if (req_stb) begin
            if (req_write) begin
              axil_awaddr  <= req_addr;
              axil_wdata   <= req_wdata;
              axil_awvalid <= 1'b1;
              axil_wvalid  <= 1'b1;
              aw_done      <= 1'b0;
              w_done       <= 1'b0;
              state        <= ST_AW;
            end else begin
              axil_araddr  <= req_addr;
              axil_arvalid <= 1'b1;
              state        <= ST_AR;
            end
          end
        end

        ST_AW: begin
          if (axil_awvalid && axil_awready) begin
            axil_awvalid <= 1'b0;
            aw_done      <= 1'b1;
          end
          if (axil_wvalid && axil_wready) begin
            axil_wvalid <= 1'b0;
            w_done      <= 1'b1;
          end
          if ((aw_done || (axil_awvalid && axil_awready)) &&
              (w_done  || (axil_wvalid  && axil_wready))) begin
            state   <= ST_B;
            aw_done <= 1'b0;
            w_done  <= 1'b0;
          end
        end

        ST_B: if (axil_bvalid) state <= ST_IDLE;

        ST_AR: begin
          if (axil_arvalid && axil_arready) begin
            axil_arvalid <= 1'b0;
            state        <= ST_R;
          end
        end

        ST_R: begin
          if (axil_rvalid) begin
            rbuf  <= axil_rdata;
            state <= ST_IDLE;
          end
        end

        default: state <= ST_IDLE;
      endcase
    end
  end
endmodule
