// TinyTapeout pin host for one kraken_axil block.
//
// ui_in[7:0]   write data
// uio_in[0]    strobe (rising edge). Ignored while an AXI transfer is in flight.
// uio_in[3:1]  opcode
// uio_in[7:4]  gpio_in[3:0]
// uo_out[7:0]  gpio_out[7:0]
// uio_out[7:0] low byte of the last CSR read (uio_oe stays 0; the pad is an input)
//
// Opcodes:
//   1 ADDR_LO  addr[7:0]  = data, clear the write buffer
//   2 ADDR_HI  addr[11:8] = data[3:0]
//   3 DATA     push one little-endian byte into the write buffer (max 4)
//   4 WRITE    AXI write of the buffer at addr & ~3, then clear the buffer
//   5 READ     AXI read of the word at addr & ~3; uio_out becomes byte 0
//   6 SHIFT    shift the last read word down 8 bits
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
  localparam logic [2:0] OP_ADDR_LO = 3'd1;
  localparam logic [2:0] OP_ADDR_HI = 3'd2;
  localparam logic [2:0] OP_DATA    = 3'd3;
  localparam logic [2:0] OP_WRITE   = 3'd4;
  localparam logic [2:0] OP_READ    = 3'd5;
  localparam logic [2:0] OP_SHIFT   = 3'd6;

  typedef enum logic [2:0] {
    ST_IDLE,
    ST_AW,
    ST_B,
    ST_AR,
    ST_R
  } state_e;

  logic        stb_q;
  logic [11:0] addr;
  logic [31:0] wbuf;
  logic [2:0]  nbytes;
  logic [31:0] rbuf;
  state_e      state;
  logic        aw_done;
  logic        w_done;

  logic [11:0] axil_awaddr, axil_araddr;
  logic        axil_awvalid, axil_awready;
  logic [31:0] axil_wdata;
  logic [3:0]  axil_wstrb;
  logic        axil_wvalid, axil_wready;
  logic [1:0]  axil_bresp;
  logic        axil_bvalid;
  logic        axil_arvalid, axil_arready;
  logic [31:0] axil_rdata;
  logic [1:0]  axil_rresp;
  logic        axil_rvalid;

  gpio_t gpio_in, gpio_out, gpio_oe;
  logic  irq;

  wire stb_rise = uio_in[0] & ~stb_q;
  wire [2:0] op = uio_in[3:1];
  wire [11:0] addr_word = {addr[11:2], 2'b00};

  assign gpio_in = gpio_t'({28'b0, uio_in[7:4]});
  assign uo_out  = ena ? gpio_out[7:0] : 8'b0;
  assign uio_out = rbuf[7:0];
  assign uio_oe  = 8'b0;

  wire _unused = &{axil_bresp, axil_rresp, gpio_oe, irq, 1'b0};

  kraken_axil #(.NUM_SM(NUM_SM)) u_kraken (
    .clk(clk),
    .rst_n(rst_n),
    .s_axil_awaddr(axil_awaddr),
    .s_axil_awvalid(axil_awvalid),
    .s_axil_awready(axil_awready),
    .s_axil_wdata(axil_wdata),
    .s_axil_wstrb(axil_wstrb),
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

  function automatic logic [3:0] wstrb_of(input logic [2:0] n);
    case (n)
      3'd1: return 4'b0001;
      3'd2: return 4'b0011;
      3'd3: return 4'b0111;
      3'd4: return 4'b1111;
      default: return 4'b0000;
    endcase
  endfunction

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      stb_q         <= 1'b0;
      addr          <= '0;
      wbuf          <= '0;
      nbytes        <= '0;
      rbuf          <= '0;
      state         <= ST_IDLE;
      aw_done       <= 1'b0;
      w_done        <= 1'b0;
      axil_awaddr   <= '0;
      axil_awvalid  <= 1'b0;
      axil_wdata    <= '0;
      axil_wstrb    <= '0;
      axil_wvalid   <= 1'b0;
      axil_araddr   <= '0;
      axil_arvalid  <= 1'b0;
    end else begin
      stb_q <= uio_in[0];

      unique case (state)
        ST_IDLE: begin
          if (stb_rise) begin
            unique case (op)
              OP_ADDR_LO: begin
                addr[7:0] <= ui_in;
                wbuf      <= '0;
                nbytes    <= '0;
              end
              OP_ADDR_HI: addr[11:8] <= ui_in[3:0];
              OP_DATA: begin
                if (nbytes < 3'd4) begin
                  wbuf[8*nbytes +: 8] <= ui_in;
                  nbytes <= nbytes + 3'd1;
                end
              end
              OP_WRITE: begin
                if (nbytes != 3'd0) begin
                  axil_awaddr  <= addr_word;
                  axil_wdata   <= wbuf;
                  axil_wstrb   <= wstrb_of(nbytes);
                  axil_awvalid <= 1'b1;
                  axil_wvalid  <= 1'b1;
                  aw_done      <= 1'b0;
                  w_done       <= 1'b0;
                  state        <= ST_AW;
                end
              end
              OP_READ: begin
                axil_araddr  <= addr_word;
                axil_arvalid <= 1'b1;
                state        <= ST_AR;
              end
              OP_SHIFT: rbuf <= {8'b0, rbuf[31:8]};
              default: ;
            endcase
          end
        end

        ST_AW: begin
          if (!aw_done) begin
            axil_awvalid <= 1'b1;
            if (axil_awvalid && axil_awready) begin
              axil_awvalid <= 1'b0;
              aw_done      <= 1'b1;
            end
          end
          if (!w_done) begin
            axil_wvalid <= 1'b1;
            if (axil_wvalid && axil_wready) begin
              axil_wvalid <= 1'b0;
              w_done      <= 1'b1;
            end
          end
          if ((aw_done || (axil_awvalid && axil_awready)) &&
              (w_done  || (axil_wvalid  && axil_wready))) begin
            state   <= ST_B;
            aw_done <= 1'b0;
            w_done  <= 1'b0;
            wbuf    <= '0;
            nbytes  <= '0;
          end
        end

        ST_B: begin
          if (axil_bvalid) state <= ST_IDLE;
        end

        ST_AR: begin
          axil_arvalid <= 1'b1;
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
