// Synchronous 2-wire host link: SCK plus one bidirectional SDIO line.
//
// A frame is 56 bits, shifted MSB first, sampled on the rising edge of SCK:
//
//   bits 55:48   {dir, 3'b000, addr[11:8]}   dir 1 = write, 0 = read
//   bits 47:40   addr[7:0]
//   bits 39:32   turnaround; the host releases SDIO, the device takes it on reads
//   bits 31:0    data, MSB first
//
// Reads start the CSR access at bit index 16, so the eight turnaround bits give
// the bus time to answer before the device drives bit index 24. Writes issue the
// CSR access after the last data bit. The device changes SDIO on the falling
// edge of SCK so the host can sample on the rising edge.
//
// SCK must stay at or below clk/4. After IDLE_CYCLES with no SCK edge the bit
// counter resets, so an aborted frame cannot desynchronise the link forever.
module kraken_serial_host #(
  parameter int unsigned IDLE_CYCLES = 64
) (
  input  logic clk,
  input  logic rst_n,

  input  logic sck_pad,
  input  logic sdio_pad,
  output logic sdio_out,
  output logic sdio_oe,

  output logic        req_stb,
  output logic        req_write,
  output logic [11:0] req_addr,
  output logic [31:0] req_wdata,
  input  logic [31:0] rsp_data
);
  localparam logic [5:0] HDR_BITS   = 6'd16;
  localparam logic [5:0] DATA_LSB   = 6'd24;
  localparam logic [5:0] FRAME_BITS = 6'd56;

  logic [1:0]  sck_sync, sdio_sync;
  logic        sck_q;
  logic [5:0]  bit_cnt;
  logic [15:0] hdr;
  logic [31:0] wshift, oshift;
  logic        dir_r;
  logic [15:0] idle_cnt;

  wire sck      = sck_sync[1];
  wire sdio     = sdio_sync[1];
  wire sck_rise = sck & ~sck_q;
  wire sck_fall = ~sck & sck_q;

  // bit_cnt has already advanced when the falling edge arrives, so it names the
  // bit the device must present next.
  wire in_data = (bit_cnt >= DATA_LSB);
  wire drive   = !dir_r && in_data;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      sck_sync  <= '0;
      sdio_sync <= '0;
      sck_q     <= 1'b0;
      bit_cnt   <= '0;
      hdr       <= '0;
      wshift    <= '0;
      oshift    <= '0;
      dir_r     <= 1'b0;
      idle_cnt  <= '0;
      sdio_out  <= 1'b0;
      sdio_oe   <= 1'b0;
      req_stb   <= 1'b0;
      req_write <= 1'b0;
      req_addr  <= '0;
      req_wdata <= '0;
    end else begin
      sck_sync  <= {sck_sync[0], sck_pad};
      sdio_sync <= {sdio_sync[0], sdio_pad};
      sck_q     <= sck;
      req_stb   <= 1'b0;

      if (sck_rise || sck_fall) idle_cnt <= '0;
      else if (idle_cnt != IDLE_CYCLES[15:0]) idle_cnt <= idle_cnt + 16'd1;

      if (idle_cnt == IDLE_CYCLES[15:0]) begin
        bit_cnt <= '0;
        sdio_oe <= 1'b0;
      end

      if (sck_rise) begin
        if (bit_cnt == 6'd0) dir_r <= sdio;
        if (bit_cnt < HDR_BITS) hdr <= {hdr[14:0], sdio};
        if (in_data) wshift <= {wshift[30:0], sdio};

        if (bit_cnt == HDR_BITS && !dir_r) begin
          req_stb   <= 1'b1;
          req_write <= 1'b0;
          req_addr  <= {hdr[11:2], 2'b00};
        end

        if (bit_cnt == (FRAME_BITS - 6'd1) && dir_r) begin
          req_stb   <= 1'b1;
          req_write <= 1'b1;
          req_addr  <= {hdr[11:2], 2'b00};
          req_wdata <= {wshift[30:0], sdio};
        end

        bit_cnt <= (bit_cnt == (FRAME_BITS - 6'd1)) ? 6'd0 : (bit_cnt + 6'd1);
      end

      if (sck_fall) begin
        sdio_oe <= drive;
        if (drive) begin
          if (bit_cnt == DATA_LSB) begin
            sdio_out <= rsp_data[31];
            oshift   <= {rsp_data[30:0], 1'b0};
          end else begin
            sdio_out <= oshift[31];
            oshift   <= {oshift[30:0], 1'b0};
          end
        end
      end
    end
  end
endmodule
