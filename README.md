# SparseMAC — Zero-Skipping INT8 MAC Array

[![CI](https://github.com/katepallewarprathmesh-sketch/SparseMAC/actions/workflows/ci.yml/badge.svg)](https://github.com/katepallewarprathmesh-sketch/SparseMAC/actions/workflows/ci.yml)

A parameterized INT8 matrix-vector accelerator, `y = W x`, with dense and activation zero-skipping modes in the same RTL. Column broadcast keeps every output lane busy when a nonzero input is issued; the bitmap scheduler skips zero-valued columns.

## Results at a glance

| Measurement | Result | Reproducible evidence |
|---|---:|---|
| Compute cycles, dense mode (`M=32`) | 32 per vector | `results/cycles_vs_sparsity.csv` |
| Compute cycles, skip mode | Equal to `nnz(x)` | `results/cycles_vs_sparsity.csv` |
| Testbench coverage bins | 19/19 hit | `results/coverage_summary.txt` |
| Scheduler formal properties | PASS by k-induction | `results/formal_summary.txt`, `results/formal_*.log` |
| Generic synthesized cell count | 498 cells | `results/ppa.json`, `results/ppa_summary.txt` |
| Toggle-count energy proxy crossover | About 3.9% sparsity | `results/power_vs_sparsity.csv` |

At 50% sparsity the normalized energy proxy is 10.8 for skip mode versus 33.6 for dense mode (about 3.1× lower); at 75% sparsity it is about 6× lower. The energy experiment uses a normalized toggle-count model, and the 498-cell figure is the structural count from generic Yosys synthesis.

## Architecture

- Column-broadcast dataflow: issuing column `j` updates all `N` accumulators with `W[i][j] * x[j]`.
- Bitmap plus find-first-set scheduler issues one nonzero column per cycle.
- `ACC_W = 2*DATA_W + $clog2(M)`; at `DATA_W=8`, `M=32`, the accumulator is 21 bits.
- Operand isolation suppresses multiplier input activity for skipped values.
- Ready/valid vector input and output interfaces support back-pressure.

## Verify and reproduce

```sh
make test      # Verilator lint and cocotb regression
make formal    # SymbiYosys scheduler proof (sby + z3)
make results   # regenerate synthesis, energy/cycle tables and plots
make clean
```

The scheduler proof checks that cleared bitmap bits are never issued, set bits are not issued twice, and the initial set is fully issued when the drain completes. The measured energy results are an RTL toggle-count proxy with normalized weights; physical-library power and timing analysis are separate follow-on measurements.

## Next design points

Pipeline the find-first-set path and compare latency/frequency, evaluate a physical technology library flow, and expand the commercial UVM port alongside the runnable cocotb flow.

## License

Apache-2.0. See [LICENSE](LICENSE).
