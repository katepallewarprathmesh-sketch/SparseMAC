# SparseMAC Specification

## 1. Overview
Zero-skipping INT8 matrix-vector accelerator. Computes `y = W x` where
`W` is an `N x M` INT8 matrix (preloaded) and `x` is an `M`-element INT8
vector (streamed). Dense mode issues all `M` columns; skip mode issues
only nonzero `x[j]`, so compute cycles track `nnz(x)`, not `M`.

## 2. Parameters
| Parameter | Default | Meaning |
|---|---|---|
| `N` | 4 | rows / MAC lanes |
| `M` | 32 | max vector length |
| `DATA_W` | 8 | operand width (signed) |
| `ACC_W` | `2*DATA_W + $clog2(M)` = 21 | accumulator width (derived, ADR-0004) |

## 3. Interface
| Signal | Dir | Width | Description |
|---|---|---|---|
| `clk`, `rst_n` | in | 1 | clock; async active-low reset |
| `x_valid`, `x_ready` | in/out | 1 | input stream handshake |
| `x_data` | in | 8 | one dense-order element per beat |
| `x_last` | in | 1 | last element of vector |
| `w_we`, `w_row`, `w_col`, `w_data` | in | 1/2/5/8 | weight write port |
| `y_valid`, `y_ready` | out/in | 1 | output handshake |
| `y_data` | out | `N*ACC_W` | packed accumulators, lane 0 in LSBs |
| `csr_mode` | in | 1 | 0=dense, 1=skip (sampled at vector start) |
| `csr_vec_len` | in | 6 | vector length 1..M (sampled at vector start) |
| `csr_cycles` | out | 32 | cumulative compute cycles |
| `csr_nnz` | out | 32 | cumulative nonzero elements seen |
| `csr_skipped` | out | 32 | cumulative elements skipped |

## 4. Protocol
- `x_ready` is high only in COLLECT. A beat is accepted when
  `x_valid && x_ready` at a rising edge.
- `y_valid` is asserted in OUTPUT and held until `y_ready` (never drops
  early). Accumulators clear only on the `y_valid && y_ready` edge.
- `csr_mode` / `csr_vec_len` are latched when the last `x` beat is
  accepted; mid-vector changes are ignored (asserted in verification).

## 5. Timing
```
COLLECT (M beats) -> COMPUTE (dense: vec_len cycles / skip: nnz cycles)
                  -> OUTPUT (y_valid until y_ready) -> COLLECT
```
Skip-mode compute latency = `nnz + 2` cycles (scheduler start + drain
handshake). Dense = `vec_len` cycles. All-zero vector in skip mode:
0 compute cycles, `y = 0`.

## 6. Arithmetic
Signed 8x8 products (16 bits) summed into 21-bit accumulators.
Max |sum| for `M=32` is `32 * 128 * 128 = 524288 < 2^20`, so overflow
is impossible and no saturation logic exists.

## 7. Counters
`csr_cycles` counts COMPUTE issue cycles (dense: `vec_len`/vector,
skip: `nnz`/vector). `csr_nnz` / `csr_skipped` accumulate over all
completed vectors. Invariant: `cycles >= nnz` per vector.
