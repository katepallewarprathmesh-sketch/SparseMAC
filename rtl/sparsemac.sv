// sparsemac.sv
// SparseMAC: zero-skipping INT8 matrix-vector MAC array.  y = W x
//   W : N x M INT8 (preloaded via w_* port)
//   x : M-element INT8 vector (streamed, dense order, valid/ready)
//   y : N accumulators (valid/ready)
//
// Dataflow: column-broadcast (outer-product). For each issued column j,
// every lane i does acc[i] += W[i][j] * x[j]. Skipping x[j]==0 therefore
// skips an entire column of work with one scheduler decision (ADR-0001).
//
// Modes (csr_mode, sampled at vector start; mid-vector changes are ignored):
//   0 = dense : issues all vec_len columns (A/B baseline, same RTL)
//   1 = skip  : issues only nonzero x[j] via sparse_scheduler (ADR-0002/3)
//
// Accumulator width (ADR-0004): ACC_W = 2*DATA_W + $clog2(M).
//   A signed 8x8 product needs 16 bits; summing up to M of them adds
//   ceil(log2(M)) bits. For M=32: ACC_W=21, overflow is impossible.
//
// Operand isolation (R7): MAC inputs are forced to zero whenever no column
// is issuing (idle / drained scheduler), cutting switching activity.
// Back-pressure (R8): x_ready is high only in COLLECT; y_valid is held
// until y_ready; accumulators are cleared only on the y handshake.
`timescale 1ns/1ps

module sparsemac #(
    parameter int N      = 4,   // rows / MAC lanes
    parameter int M      = 32,  // max vector length
    parameter int DATA_W = 8    // INT8
) (
    input  logic                  clk,
    input  logic                  rst_n,

    // Input stream (dense order, one element per beat)
    input  logic                  x_valid,
    output logic                  x_ready,
    input  logic [DATA_W-1:0]     x_data,
    input  logic                  x_last,

    // Weight load port
    input  logic                  w_we,
    input  logic [$clog2(N)-1:0]  w_row,
    input  logic [$clog2(M)-1:0]  w_col,
    input  logic [DATA_W-1:0]     w_data,

    // Output vector
    output logic                  y_valid,
    input  logic                  y_ready,
    output logic [N*ACC_W-1:0]    y_data,

    // CSR-style control / counters
    input  logic                  csr_mode,        // 0=dense, 1=skip
    input  logic [$clog2(M+1)-1:0] csr_vec_len,   // 1..M
    output logic [31:0]           csr_cycles,      // compute cycles (cumulative)
    output logic [31:0]           csr_nnz,         // nonzero elements seen (cumulative)
    output logic [31:0]           csr_skipped      // elements skipped (cumulative)
);
    localparam int ACC_W = 2*DATA_W + $clog2(M);
    localparam int IDX_W = $clog2(M);
    localparam int LEN_W = $clog2(M+1);

    // ---- Weight buffer: flop array (ADR-0006; SRAM is future work) ----
    logic signed [DATA_W-1:0] w_buf [0:N*M-1];
    always_ff @(posedge clk) begin
        if (w_we)
            w_buf[int'(w_row)*M + int'(w_col)] <= $signed(w_data);
    end

    // ---- Input buffer + bitmap ----
    logic signed [DATA_W-1:0] x_buf [0:M-1];
    logic [M-1:0]             bitmap;
    logic [LEN_W-1:0]         vec_len_q;   // latched at vector start
    logic                     mode_q;      // latched at vector start
    logic [IDX_W-1:0]         x_idx;
    logic [IDX_W-1:0]         last_idx;

    // Subtract at index width. Truncation is intentional for power-of-two M:
    // vec_len=M wraps to index M-1 (e.g. 32 -> 31).
    always_comb begin
        last_idx = vec_len_q[IDX_W-1:0] - IDX_W'(1);
    end

    // ---- Accumulators ----
    logic signed [ACC_W-1:0]  acc [0:N-1];

    // ---- FSM ----
    typedef enum logic [1:0] {ST_COLLECT, ST_COMPUTE, ST_OUTPUT} state_t;
    state_t state;

    // ---- Scheduler (skip mode) ----
    logic             sched_start;
    logic             sched_issue_valid;
    logic [IDX_W-1:0] sched_issue_idx;
    logic             sched_done;
    sparse_scheduler #(.M(M)) u_sched (
        .clk         (clk),
        .rst_n       (rst_n),
        .bitmap_in   (bitmap),
        .start       (sched_start),
        .issue_valid (sched_issue_valid),
        .issue_idx   (sched_issue_idx),
        .done        (sched_done)
    );

    // ---- Dense-mode column counter ----
    logic [IDX_W-1:0] dense_j;

    // ---- Issue mux: which column issues this cycle? ----
    logic             issuing;
    logic [IDX_W-1:0] issue_j;
    always_comb begin
        if (mode_q == 1'b1) begin          // skip
            issuing = sched_issue_valid;
            issue_j = sched_issue_idx;
        end else begin                     // dense
            issuing = (state == ST_COMPUTE);
            issue_j = dense_j;
        end
    end

    // ---- MAC lanes with operand isolation ----
    // When not issuing, both operands are forced to zero (R7).
    logic signed [DATA_W-1:0] mac_x;
    always_comb mac_x = issuing ? x_buf[issue_j] : '0;

    genvar gi;
    generate
        for (gi = 0; gi < N; gi++) begin : g_lane
            logic signed [DATA_W-1:0] mac_w;
            logic signed [2*DATA_W-1:0] prod;
            always_comb begin
                mac_w = issuing ? w_buf[gi*M + int'(issue_j)] : '0;
                prod  = mac_x * mac_w;   // signed x signed -> signed product
            end
            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n)
                    acc[gi] <= '0;
                else if (state == ST_COMPUTE && issuing)
                    acc[gi] <= acc[gi] + ACC_W'($signed(prod));
                else if (state == ST_OUTPUT && y_valid && y_ready)
                    acc[gi] <= '0;        // cleared after output handshake
            end
        end
    endgenerate

    // ---- Output packing ----
    always_comb begin
        for (int i = 0; i < N; i++)
            y_data[i*ACC_W +: ACC_W] = acc[i];
    end

    // ---- Counters ----
    logic [31:0] cycles_q, nnz_q, skipped_q;
    logic [31:0] popcount_bitmap;
    always_comb begin
        popcount_bitmap = 32'd0;
        for (int k = 0; k < M; k++)
            popcount_bitmap += bitmap[k] ? 32'd1 : 32'd0;
    end
    assign csr_cycles  = cycles_q;
    assign csr_nnz     = nnz_q;
    assign csr_skipped = skipped_q;

    // ---- FSM + interface ----
    assign x_ready = (state == ST_COLLECT);
    assign y_valid = (state == ST_OUTPUT);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= ST_COLLECT;
            x_idx       <= '0;
            bitmap      <= '0;
            vec_len_q   <= LEN_W'(M);
            mode_q      <= 1'b0;
            dense_j     <= '0;
            cycles_q    <= 32'd0;
            nnz_q       <= 32'd0;
            skipped_q   <= 32'd0;
        end else begin
            unique case (state)
                ST_COLLECT: begin
                    if (x_valid && x_ready) begin
                        x_buf[x_idx] <= $signed(x_data);
                        bitmap[x_idx] <= (x_data != '0);
                        if (x_last || (x_idx == last_idx)) begin
                            // Vector complete: latch control, start compute.
                            // NOTE: bitmap update above is nonblocking, so the
                            // scheduler is started next cycle from the updated
                            // bitmap via the sched_start pulse in ST_COMPUTE entry.
                            vec_len_q   <= csr_vec_len;
                            mode_q      <= csr_mode;
                            dense_j     <= '0;
                            x_idx       <= '0;
                            state       <= ST_COMPUTE;
                        end else begin
                            x_idx <= x_idx + 1'b1;
                        end
                    end
                end

                ST_COMPUTE: begin
                    // Count one compute cycle per issue (dense: vec_len, skip: nnz).
                    if (issuing)
                        cycles_q <= cycles_q + 32'd1;
                    if (mode_q == 1'b0) begin  // dense
                        if (dense_j == last_idx) begin
                            state <= ST_OUTPUT;
                            // Update counters from the collected bitmap.
                            nnz_q     <= nnz_q + popcount_bitmap;
                            skipped_q <= skipped_q + (32'(vec_len_q) - popcount_bitmap);
                        end else begin
                            dense_j <= dense_j + 1'b1;
                        end
                    end else begin             // skip
                        if (sched_done) begin
                            state <= ST_OUTPUT;
                            nnz_q     <= nnz_q + popcount_bitmap;
                            skipped_q <= skipped_q + (32'(vec_len_q) - popcount_bitmap);
                        end
                    end
                end

                ST_OUTPUT: begin
                    if (y_valid && y_ready) begin
                        bitmap <= '0;   // ready for next vector
                        state  <= ST_COLLECT;
                    end
                end

                default: state <= ST_COLLECT;
            endcase
        end
    end

    // Scheduler start pulse: one cycle after entering COMPUTE in skip mode,
    // so bitmap_in reflects the fully collected vector.
    logic compute_entered;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            compute_entered <= 1'b0;
            sched_start     <= 1'b0;
        end else begin
            sched_start <= 1'b0;
            if (state == ST_COMPUTE && !compute_entered) begin
                compute_entered <= 1'b1;
                if (mode_q == 1'b1)
                    sched_start <= 1'b1;
            end else if (state != ST_COMPUTE) begin
                compute_entered <= 1'b0;
            end
        end
    end
endmodule
