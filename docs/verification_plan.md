# SparseMAC Verification Plan

| Feature | Directed / random tests | Coverage points | Assertions |
|---|---|---|---|
| Correct math | Random W, x vs NumPy `W@x` | value bins -128/-1/0/1/127 | scoreboard equality |
| Zero-skip | sparsity sweep 0/25/50/75/95/100% x dense/skip | sparsity x mode cross | skip cycles == nnz; dense == M |
| Edge vectors | all-zero, all-nonzero, single nz at 0/mid/M-1 | each case hit | y produced for all-zero |
| Back-pressure | random x bubble, y_ready stall | stall bins | y_valid stable until ready |
| Back-to-back | consecutive vectors, no gap | gap bins | acc cleared after output |
| Mode switch | change mode between vectors | transition cross | mid-vector change ignored |
| Counters | CSR vs TB-computed | nnz bins | cycles >= nnz |
| Liveness | any accepted vector | n/a | output within nnz+K cycles |

## Tracks
- **Track B (runnable here):** cocotb + Verilator, `tb_cocotb/test_sparsemac.py`.
  Scoreboard against NumPy golden model (`scripts/golden_model.py`).
- **Track A (licensed tools):** UVM skeleton in `tb_uvm/` for VCS/Questa.
  Same sequences, same golden vectors. Not run in this environment
  (no VCS/Questa); see `tb_uvm/README.md`.
- **Formal:** SymbiYosys on `sparse_scheduler` (P1/P2a/P2b, k-induction PASS).
