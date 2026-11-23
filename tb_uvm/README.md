# Track A (UVM) - skeleton for licensed tools

This environment has no VCS/Questa, so Track A is a structured skeleton,
not a run. It mirrors Track B exactly (same spec, same golden vectors):

- `x_agent`: sequence item with a `sparsity` knob + constraint; drives
  the dense x stream with random back-pressure.
- `w_agent`: preloads W through the weight port.
- `y_monitor` + scoreboard: SystemVerilog reference model checked
  against NumPy-generated vector files (`scripts/golden_model.py`).
- Covergroups: sparsity x mode cross, value bins, stall bins.

To run: point VCS/Questa at `rtl/*.sv` + this directory, compile with
`-sv_lib` UVM, run the sparsity-sweep sequence. Expected result must
match Track B cycle counts (dense=M, skip=nnz) - disagreement between
tracks is a bug in one of them.
