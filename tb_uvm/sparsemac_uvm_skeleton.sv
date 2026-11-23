// sparsemac_uvm_skeleton.sv - Track A skeleton (VCS/Questa only).
// Not compiled in the open-source flow. See tb_uvm/README.md.
`timescale 1ns/1ps

class x_item extends uvm_sequence_item;
    rand int unsigned sparsity_pct;  // 0..100
    rand bit [7:0] data [];
    constraint c_sparsity { sparsity_pct inside {[0:100]}; }
    constraint c_len { data.size() == 32; }
    `uvm_object_utils(x_item)
endclass

class sparsemac_scoreboard extends uvm_scoreboard;
    // Reference model: y = W @ x in int32, checked against the
    // NumPy-generated vector files from scripts/golden_model.py.
    // Covergroups: sparsity x mode, value bins, stall bins.
    `uvm_component_utils(sparsemac_scoreboard)
endclass
