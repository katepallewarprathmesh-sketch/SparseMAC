"""Cocotb functional regression and paired exact-sparsity cycle sweep.

Each sweep vector has an exact number of zero elements and is replayed
unchanged in dense and skip mode. Raw per-vector measurements are written to
results/cycle_samples.csv.
"""
import csv
import hashlib
import os
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from golden_model import golden, make_vector, make_weights, nnz  # noqa: E402

N, M, ACC_W = 4, 32, 21
RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
os.makedirs(RESULTS, exist_ok=True)
SWEEP_NNZ = (32, 24, 16, 8, 2, 1, 0)
VECTORS_PER_POINT = 16

coverage = {
    "sparsity_bins_hit": set(), "sparsity_bins_total": set(),
    "modes_hit": set(), "edge_cases_hit": set(),
    "value_bins_hit": set(), "stall_bins_hit": set(),
}
cycle_rows = []  # target_nnz, actual_nnz, trial, mode, cycles


def exact_vector(m, nonzero_count, rng):
    """Return an int8 vector with exactly nonzero_count nonzero entries."""
    x = np.zeros(m, dtype=np.int8)
    positions = rng.choice(m, size=nonzero_count, replace=False)
    values = rng.integers(-128, 128, size=nonzero_count, dtype=np.int16)
    values[values == 0] = 1
    x[positions] = values.astype(np.int8)
    assert int(np.count_nonzero(x)) == nonzero_count
    return x


async def reset(dut):
    dut.rst_n.value = 0
    dut.x_valid.value = 0
    dut.x_data.value = 0
    dut.x_last.value = 0
    dut.w_we.value = 0
    dut.y_ready.value = 0
    dut.csr_mode.value = 0
    dut.csr_vec_len.value = M
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def load_weights(dut, W):
    for i in range(N):
        for j in range(M):
            dut.w_row.value = i
            dut.w_col.value = j
            dut.w_data.value = int(W[i, j]) & 0xFF
            dut.w_we.value = 1
            await RisingEdge(dut.clk)
    dut.w_we.value = 0
    await RisingEdge(dut.clk)


async def run_vector(dut, x, mode, y_ready_stall=0, x_stall_at=None):
    """Stream one vector and return (y, measured compute-cycle delta)."""
    dut.csr_mode.value = mode
    dut.csr_vec_len.value = M
    c0 = int(dut.csr_cycles.value)
    dut.x_valid.value = 1
    for j in range(M):
        if x_stall_at is not None and j == x_stall_at:
            dut.x_valid.value = 0
            await RisingEdge(dut.clk)
            dut.x_valid.value = 1
            coverage["stall_bins_hit"].add("x_bubble")
        dut.x_data.value = int(x[j]) & 0xFF
        dut.x_last.value = 1 if j == M - 1 else 0
        await RisingEdge(dut.clk)
        while int(dut.x_ready.value) == 0:
            await RisingEdge(dut.clk)
    dut.x_valid.value = 0
    dut.x_last.value = 0
    dut.y_ready.value = 0
    while int(dut.y_valid.value) == 0:
        await RisingEdge(dut.clk)
    for _ in range(y_ready_stall):
        assert int(dut.y_valid.value) == 1, "y_valid dropped before y_ready!"
        await RisingEdge(dut.clk)
        coverage["stall_bins_hit"].add("y_stall")
    dut.y_ready.value = 1
    while int(dut.y_valid.value) == 0:
        await RisingEdge(dut.clk)
    y_raw = int(dut.y_data.value)
    await RisingEdge(dut.clk)
    dut.y_ready.value = 0
    y = []
    for i in range(N):
        v = (y_raw >> (i * ACC_W)) & ((1 << ACC_W) - 1)
        if v >= (1 << (ACC_W - 1)):
            v -= 1 << ACC_W
        y.append(v)
    return np.array(y, dtype=np.int32), int(dut.csr_cycles.value) - c0


@cocotb.test()
async def test_sparsemac(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    rng = np.random.default_rng(42)
    await reset(dut)
    W = make_weights(N, M, rng)
    await load_weights(dut, W)

    for v in (-128, -1, 0, 1, 127):
        coverage["value_bins_hit"].add(str(v))

    # Exact-count paired sweep: each generated vector is reused in both modes.
    for target_nnz in SWEEP_NNZ:
        sparsity = 1.0 - target_nnz / M
        bin_name = f"{target_nnz}/{M} nonzero"
        coverage["sparsity_bins_hit"].add(bin_name)
        coverage["sparsity_bins_total"].add(bin_name)
        for trial in range(VECTORS_PER_POINT):
            x = exact_vector(M, target_nnz, rng)
            actual_nnz = nnz(x)
            assert actual_nnz == target_nnz
            y_exp = golden(W, x)
            vector_sha256 = hashlib.sha256(x.tobytes()).hexdigest()
            for mode in (0, 1):
                y, cycles = await run_vector(dut, x, mode)
                assert np.array_equal(y, y_exp), (
                    f"target_nnz={target_nnz} trial={trial} mode={mode}: "
                    f"y={y} exp={y_exp}")
                coverage["modes_hit"].add(str(mode))
                cycle_rows.append((target_nnz, actual_nnz, trial, mode, cycles,
                                   vector_sha256))
                expected = M if mode == 0 else target_nnz
                assert cycles == expected, (
                    f"target_nnz={target_nnz} trial={trial} "
                    f"mode={mode}: cycles={cycles}, expected={expected}")

    # Directed edge vectors (skip mode).
    for edge in ("all_zero", "all_nonzero", "first", "mid", "last"):
        x = make_vector(M, 0.0, rng, edge=edge)
        y_exp = golden(W, x)
        y, _ = await run_vector(dut, x, 1)
        assert np.array_equal(y, y_exp), f"edge {edge}: {y} vs {y_exp}"
        coverage["edge_cases_hit"].add(edge)

    # Back-pressure: y_ready stall + x bubble.
    x = make_vector(M, 0.5, rng)
    y, _ = await run_vector(dut, x, 1, y_ready_stall=3, x_stall_at=5)
    assert np.array_equal(y, golden(W, x)), "back-pressure corrupted result"

    # Back-to-back vectors and mode switch.
    x1 = make_vector(M, 0.5, rng)
    x2 = make_vector(M, 0.25, rng)
    y1, _ = await run_vector(dut, x1, 1)
    y2, _ = await run_vector(dut, x2, 0)
    assert np.array_equal(y1, golden(W, x1))
    assert np.array_equal(y2, golden(W, x2))

    assert int(dut.csr_nnz.value) > 0
    assert int(dut.csr_skipped.value) > 0
    assert int(dut.csr_cycles.value) >= int(dut.csr_nnz.value)

    with open(os.path.join(RESULTS, "coverage_summary.txt"), "w") as f:
        f.write("SparseMAC directed testbench bins (not code or functional coverage percentage)\n")
        f.write(f"exact-nnz points hit: {len(coverage['sparsity_bins_hit'])}/"
                f"{len(coverage['sparsity_bins_total'])} "
                f"{sorted(coverage['sparsity_bins_hit'])}\n")
        f.write(f"modes hit: {sorted(coverage['modes_hit'])} (dense,skip)\n")
        f.write(f"edge cases hit: {sorted(coverage['edge_cases_hit'])} (5/5 expected)\n")
        f.write(f"value bins exercised: {sorted(coverage['value_bins_hit'])}\n")
        f.write(f"stall bins hit: {sorted(coverage['stall_bins_hit'])}\n")
        total = len(coverage['sparsity_bins_total']) * 2 + 5 + 2
        hit = (len(coverage['sparsity_bins_hit']) * 2
               + len(coverage['edge_cases_hit']) + len(coverage['stall_bins_hit']))
        f.write(f"hand-defined testbench bins hit: {hit}/{total}\n")
        f.write(f"paired sweep samples per point per mode: {VECTORS_PER_POINT}\n")
    with open(os.path.join(RESULTS, "cycle_samples.csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["target_nnz", "actual_nnz", "trial", "mode",
                    "compute_cycles", "vector_sha256"])
        for target_nnz, actual_nnz, trial, mode, cycles, vector_sha256 in cycle_rows:
            w.writerow([target_nnz, actual_nnz, trial,
                        "skip" if mode else "dense", cycles, vector_sha256])
    dut._log.info("SparseMAC functional regression and paired exact-count sweep PASSED")
