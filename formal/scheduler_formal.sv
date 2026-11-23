// scheduler_formal.sv
// Formal wrapper for sparse_scheduler (SymbiYosys).
// Properties:
//   P1: an issue never fires for a cleared bitmap bit.
//   P2: every set bit is issued exactly once (ghost issued-mask tracking).
//   P3: termination is bounded (checked by BMC depth in the .sby file).
`timescale 1ns/1ps

module scheduler_formal #(
    parameter int M = 8   // small M keeps BMC tractable; RTL is parameterized
) (
    input logic clk
);
    logic rst_n;
    logic [M-1:0] bitmap_in;
    logic start;
    logic issue_valid;
    logic [$clog2(M)-1:0] issue_idx;
    logic done;

    sparse_scheduler #(.M(M)) dut (
        .clk(clk), .rst_n(rst_n), .bitmap_in(bitmap_in), .start(start),
        .issue_valid(issue_valid), .issue_idx(issue_idx), .done(done)
    );

    // Ghost state: initial bitmap + issued mask (formal only).
    logic [M-1:0] init_bitmap;
    logic [M-1:0] issued_mask;
    logic         armed;

    always @(posedge clk) begin
        if (!rst_n) begin
            armed <= 0;
            issued_mask <= 0;
            init_bitmap <= 0;
        end else begin
            if (start) begin
                init_bitmap <= bitmap_in;
                issued_mask <= 0;
                armed <= 1;
            end
            if (issue_valid)
                issued_mask[issue_idx] <= 1'b1;
        end
    end

    always @(posedge clk) begin
        if (rst_n) begin
            // P1: issued bit was set in the initial bitmap.
            if (armed && issue_valid)
                assert (init_bitmap[issue_idx] == 1'b1);
            // P2a: no bit is issued twice.
            if (armed && issue_valid)
                assert (issued_mask[issue_idx] == 1'b0);
            // P2b: when done, issued == initial (nothing missed).
            // The final issue lands in the same cycle as `done`, so include
            // the current-cycle issue in the comparison.
            if (armed && done)
                assert ((issued_mask |
                         (issue_valid ? (M'(1) << issue_idx) : '0)) == init_bitmap);
        end
    end

    // Assumptions: reset is asserted at time zero; start pulses once after
    // reset; bitmap stable during drain.
    always @(posedge clk) begin
        if ($initstate) begin
            assume (!rst_n);
            assume (!start);
        end
    end
    // start is a single-cycle pulse, issued once per drain (the top FSM
    // guarantees this; a mid-drain re-start is out of contract).
    reg started;
    always @(posedge clk) begin
        if (!rst_n) started <= 0;
        else if (start) started <= 1;
    end
    always @(posedge clk) begin
        if (started)
            assume (!start);
    end
    reg past_start;
    always @(posedge clk) begin
        if (!rst_n) past_start <= 0;
        else past_start <= start;
    end
    always @(posedge clk) begin
        if (past_start && !start)
            assume (bitmap_in == $past(bitmap_in));
    end
endmodule
