# SparseMAC — Zero-Skipping INT8 MAC Array

[![CI](https://github.com/katepallewarprathmesh-sketch/SparseMAC/actions/workflows/ci.yml/badge.svg)](https://github.com/katepallewarprathmesh-sketch/SparseMAC/actions/workflows/ci.yml)

A parameterized INT8 matrix-vector accelerator, `y = W x`, with dense and activation zero-skipping modes in the same RTL. Column broadcast updates every output lane for each issued nonzero input; the bitmap scheduler skips zero-valued columns.

## Measured and verified evidence

| Check | Result | Evidence |
|---|---|---|
| Compute cycles | Dense: 32 cycles; skip: exactly `nnz(x)` cycles | `results/cycle_samples.csv`, `results/cycles_vs_sparsity.csv` |
| Paired exact-count sweep | 16 vectors per point per mode; seven exact `nnz` points from 32 to 0; each vector replayed in both modes | Raw CSV includes SHA-256 vector identity |
| Testbench checks | 21/21 hand-defined bins hit; this is not code-coverage or a standard functional-coverage percentage | `results/coverage_summary.txt` |
| Scheduler formal | PASS by k-induction for reduced `M=8` wrapper using immediate assertions | `results/formal_summary.txt`, `results/formal_*.log` |
| Generic synthesis | 8,979 Yosys generic cells for the full synthesized design; no PDK or physical implementation | `results/ppa.json`, `results/ppa_summary.txt` |

The cycle sweep uses exact zero counts, deterministic seeded vectors, and paired dense/skip runs on the same vector. The CSV reports per-point mean, sample standard deviation, minimum and maximum; compute-cycle spread is zero in this design because its issue count is determined by the exact nonzero count.

The energy table is an **analytical scenario**, not measured power and not an RTL toggle-count proxy. It assumes normalized MAC energy, a fixed skip overhead and `nnz/M` activity; no Hamming distances or signal toggles are counted. Use `results/analytical_energy_model.csv` only as an explicit what-if model. No measured energy, power, break-even sparsity or energy-saving result is claimed. Generic cell count is also not physical area or signoff PPA.

## Architecture

- Column-broadcast dataflow: issuing column `j` updates all `N` accumulators with `W[i][j] * x[j]`.
- Bitmap plus find-first-set scheduler issues one nonzero column per cycle.
- `ACC_W = 2*DATA_W + $clog2(M)`; at `DATA_W=8`, `M=32`, the accumulator is 21 bits.
- Operand isolation suppresses multiplier inputs when no column issues.
- Ready/valid vector input and output interfaces support back-pressure.

## Reproduce

```sh
make test       # explicit-width Verilator lint + paired cocotb exact-count regression
make formal     # SymbiYosys scheduler proof (sby + z3)
make results    # rerun test, synthesize with Yosys, summarize samples and regenerate plots
make clean
```

`make results` requires a successful Yosys process and a valid nonzero cell count. A parser or synthesis failure stops the command before `ppa.json` is replaced.

## Scope and next steps

The scheduler proof checks issue validity against the initial bitmap, uniqueness, and full drain completion under its stated assumptions. These are immediate assertions in a reduced scheduler harness, not a complete SVA suite for the accelerator. `tb_uvm/` contains a small UVM skeleton and porting notes; no VCS/Questa UVM run is reported. Extending UVM, evaluating a physical library flow, and measuring RTL activity remain future work.

## Tested tool versions

Versions observed in the local reproducibility run: Verilator 5.032, Yosys 0.52, cocotb 1.9.2, Python 3.13.18, NumPy 2.3.5, Matplotlib 3.11.2, and Z3 5.4.1. The repository does not yet pin a complete toolchain image; record any different versions when reproducing.

## License

Apache-2.0. See [LICENSE](LICENSE).
