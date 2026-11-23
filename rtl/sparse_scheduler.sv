// sparse_scheduler.sv
// Find-first-set skip scheduler for SparseMAC.
// Issues each set bit of the input bitmap exactly once, lowest index first,
// one issue per cycle. Used in skip mode; dense mode bypasses it.
//
// Formal properties (see formal/scheduler_formal.sv):
//   P1: an issue never fires for a cleared bitmap bit.
//   P2: every set bit is issued exactly once (no duplicates, none missed).
//   P3: termination - bitmap reaches zero within popcount(bitmap) issues.
`timescale 1ns/1ps

module sparse_scheduler #(
    parameter int M = 32
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic [M-1:0]     bitmap_in,   // bitmap to drain (latched on start)
    input  logic             start,       // pulse: latch bitmap_in and begin
    output logic             issue_valid, // 1-cycle pulse per issue
    output logic [$clog2(M)-1:0] issue_idx, // column index issued
    output logic             done         // 1 when all bits drained
);
    localparam int IDX_W = $clog2(M);

    logic [M-1:0] bitmap_work;
    logic         active;

    // Find-first-set: lowest set bit index (combinational priority encoder).
    // This is the likely critical path for large M (see ADR-0003).
    logic [IDX_W-1:0] ffs_idx;
    logic             ffs_valid;
    always_comb begin
        ffs_idx   = '0;
        ffs_valid = 1'b0;
        for (int k = M-1; k >= 0; k--) begin
            if (bitmap_work[k]) begin
                ffs_idx   = IDX_W'(k);
                ffs_valid = 1'b1;
            end
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            bitmap_work <= '0;
            active      <= 1'b0;
            issue_valid <= 1'b0;
            issue_idx   <= '0;
            done        <= 1'b0;
        end else begin
            // issue_valid and done are 1-cycle pulses (default cleared).
            // A level `done` would go stale across vectors and the top
            // FSM would mistake the previous drain for the current one.
            issue_valid <= 1'b0;
            done        <= 1'b0;
            if (start) begin
                bitmap_work <= bitmap_in;
                active      <= 1'b1;
            end else if (active) begin
                if (ffs_valid) begin
                    issue_valid <= 1'b1;
                    issue_idx   <= ffs_idx;
                    bitmap_work[ffs_idx] <= 1'b0;  // clear issued bit
                    if (bitmap_work == ({{(M-1){1'b0}}, 1'b1} << ffs_idx)) begin
                        // This was the last set bit.
                        active <= 1'b0;
                        done   <= 1'b1;
                    end
                end else begin
                    active <= 1'b0;
                    done   <= 1'b1;
                end
            end
        end
    end
endmodule
