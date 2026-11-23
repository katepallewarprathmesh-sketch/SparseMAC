# SparseMAC — Zero-Skipping INT8 MAC Array

Zero-skipping matrix-vector accelerator (`y = W x`, INT8) with a dense
A/B baseline in the same RTL. Skip mode issues only nonzero activations,
so compute cycles track `nnz(x)`, not `M`.

## Results (measured, see `results/`)

| Claim | Evidence |
|---|---|
| Skip cycles == nnz, dense == M (M=32) | `results/cycles_vs_sparsity.csv` |
| Bin coverage 19/19 (sparsity x mode, edges, stalls) | `results/coverage_summary.txt` |
| Scheduler formal proof PASS (k-induction, P1/P2a/P2b) | `results/formal_summary.txt` |
| Yosys generic synth: 498 cells | `results/ppa.json` |
| Break-even sparsity ≈ 0.04 (energy proxy) | `results/power_vs_sparsity.csv` + plots |

At 50% sparsity, skip energy ≈ 10.8 vs dense 33.6 normalized units
(~3.1×); at 75%, ~6×. Power/energy are a **labeled toggle-count proxy**
(OpenROAD/OpenSTA unavailable here) — not signoff numbers.

## Architecture
Column-broadcast dataflow: each issued column `j` updates all `N` lanes
(`acc[i] += W[i][j]*x[j]`). Bitmap + find-first-set scheduler drains
nonzero columns at 1 issue/cycle. `ACC_W = 2*8 + $clog2(32) = 21` bits
(overflow impossible). Operand isolation holds MAC inputs at zero when
idle.

## How to reproduce
```sh
make test      # lint + cocotb/Verilator regression (smoke)
make formal    # SymbiYosys proof (needs sby + z3)
make results   # regenerate PPA/plots from measured cycles
```
The Makefile targets describe the runnable flows.

## Limitations
- Flop-array weights (SRAM is future work).
- FFS over M bits is the likely critical path; pipelining it is a
  future design-space point.
- Track A UVM is a skeleton for VCS/Questa (`tb_uvm/`); Track B is the
  fully runnable flow.
- Power is a proxy; no PDK signoff flow was run.
