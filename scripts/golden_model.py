"""Golden model for SparseMAC: y = W @ x  (NumPy, int32).

W: (N, M) int8, x: (M,) int8, y: (N,) int32.
Accumulator width check: ACC_W = 2*8 + ceil(log2(M)) bits suffice
(product needs 16 bits; summing M products adds ceil(log2(M)) bits).
"""
import numpy as np


def acc_width(m: int, data_w: int = 8) -> int:
    return 2 * data_w + int(np.ceil(np.log2(m))) if m > 1 else 2 * data_w


def golden(W: np.ndarray, x: np.ndarray) -> np.ndarray:
    W = np.asarray(W, dtype=np.int32)
    x = np.asarray(x, dtype=np.int32)
    assert W.ndim == 2 and x.ndim == 1 and W.shape[1] == x.shape[0]
    return W @ x


def nnz(x: np.ndarray) -> int:
    return int(np.count_nonzero(x))


def make_vector(m: int, sparsity: float, rng: np.random.Generator,
                edge: str | None = None) -> np.ndarray:
    """Random int8 vector with the given fraction of zeros."""
    if edge == "all_zero":
        return np.zeros(m, dtype=np.int8)
    if edge == "all_nonzero":
        v = rng.integers(-128, 128, size=m, dtype=np.int8)
        v[v == 0] = 1
        return v.astype(np.int8)
    if edge in ("first", "mid", "last"):
        v = np.zeros(m, dtype=np.int8)
        idx = {"first": 0, "mid": m // 2, "last": m - 1}[edge]
        v[idx] = np.int8(rng.integers(1, 128))
        return v
    v = rng.integers(-128, 128, size=m, dtype=np.int8)
    mask = rng.random(m) < sparsity
    v[mask] = 0
    return v.astype(np.int8)


def make_weights(n: int, m: int, rng: np.random.Generator) -> np.ndarray:
    return rng.integers(-128, 128, size=(n, m), dtype=np.int8)


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    W = make_weights(4, 32, rng)
    x = make_vector(32, 0.5, rng)
    y = golden(W, x)
    print("W shape", W.shape, "x nnz", nnz(x), "y", y)
    # Overflow check: |y| must fit in ACC_W=21 bits.
    assert np.all(np.abs(y) < 2 ** (acc_width(32) - 1)), "overflow!"
    print(f"ACC_W={acc_width(32)} bits: no overflow. OK")
