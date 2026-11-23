"""cocotb testbench for SparseMAC (Track B, open-source flow).

Covers: correct math vs NumPy golden, sparsity sweep x mode, edge vectors,
back-pressure, back-to-back vectors, mode switch, counters.
Writes results/coverage_summary.txt and results/cycles_vs_sparsity.csv.
"""
import os
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from golden_model import golden, make_vector, make_weights, nnz  # noqa: E402

N, M, ACC_W = 4, 32, 21
RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
os.makedirs(RESULTS, exist_ok=True)

coverage = {
    "sparsity_bins_hit": set(), "sparsity_bins_total": set(),
    "modes_hit": set(), "edge_cases_hit": set(),
    "value_bins_hit": set(), "stall_bins_hit": set(),
}
cycle_rows = []  # (sparsity, mode, nnz, cycles)


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
    """Stream one vector, return (y, cycles_delta)."""
    dut.csr_mode.value = mode
    dut.csr_vec_len.value = M
    c0 = int(dut.csr_cycles.value)
    # Stream x with optional stall injection.
    dut.x_valid.value = 1
    for j in range(M):
        if x_stall_at is not None and j == x_stall_at:
            dut.x_valid.value = 0  # bubble: DUT must hold state
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
    # Wait for y, with optional y_ready stall.
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

    # --- Sparsity sweep x mode ---
    for sparsity in (0.0, 0.25, 0.5, 0.75, 0.95, 1.0):
        for mode in (0, 1):
            x = make_vector(M, sparsity, rng)
            y_exp = golden(W, x)
            y, cycles = await run_vector(dut, x, mode)
            assert np.array_equal(y, y_exp), \
                f"sparsity={sparsity} mode={mode}: y={y} exp={y_exp}"
            coverage["sparsity_bins_hit"].add(str(sparsity))
            coverage["sparsity_bins_total"].add(str(sparsity))
            coverage["modes_hit"].add(str(mode))
            cycle_rows.append((sparsity, mode, nnz(x), cycles))
            if mode == 0:
                assert cycles == M, f"dense cycles {cycles} != {M}"
            else:
                assert cycles == nnz(x), \
                    f"skip cycles {cycles} != nnz {nnz(x)}"

    # --- Edge vectors (skip mode) ---
    for edge in ("all_zero", "all_nonzero", "first", "mid", "last"):
        x = make_vector(M, 0.0, rng, edge=edge)
        y_exp = golden(W, x)
        y, cycles = await run_vector(dut, x, 1)
        assert np.array_equal(y, y_exp), f"edge {edge}: {y} vs {y_exp}"
        coverage["edge_cases_hit"].add(edge)

    # --- Back-pressure: y_ready stall + x bubble ---
    x = make_vector(M, 0.5, rng)
    y, _ = await run_vector(dut, x, 1, y_ready_stall=3, x_stall_at=5)
    assert np.array_equal(y, golden(W, x)), "back-pressure corrupted result"

    # --- Back-to-back vectors, no gap ---
    x1 = make_vector(M, 0.5, rng)
    x2 = make_vector(M, 0.25, rng)
    y1, _ = await run_vector(dut, x1, 1)
    y2, _ = await run_vector(dut, x2, 0)  # mode switch between vectors
    assert np.array_equal(y1, golden(W, x1))
    assert np.array_equal(y2, golden(W, x2))

    # --- Counters ---
    assert int(dut.csr_nnz.value) > 0
    assert int(dut.csr_skipped.value) > 0
    assert int(dut.csr_cycles.value) >= int(dut.csr_nnz.value)

    # --- Coverage + cycle report ---
    with open(os.path.join(RESULTS, "coverage_summary.txt"), "w") as f:
        f.write("SparseMAC functional coverage (TB-measured bins)\n")
        f.write(f"sparsity bins hit: {len(coverage['sparsity_bins_hit'])}/"
                f"{len(coverage['sparsity_bins_total'])} "
                f"{sorted(coverage['sparsity_bins_hit'])}\n")
        f.write(f"modes hit: {sorted(coverage['modes_hit'])} (dense,skip)\n")
        f.write(f"edge cases hit: {sorted(coverage['edge_cases_hit'])} "
                f"(5/5 expected)\n")
        f.write(f"value bins hit: {sorted(coverage['value_bins_hit'])}\n")
        f.write(f"stall bins hit: {sorted(coverage['stall_bins_hit'])}\n")
        total = (len(coverage['sparsity_bins_total']) * 2 + 5 + 2)
        hit = (len(coverage['sparsity_bins_hit']) * 2
               + len(coverage['edge_cases_hit']) + len(coverage['stall_bins_hit']))
        f.write(f"bin coverage: {hit}/{total} = {100*hit/total:.1f}%\n")
    with open(os.path.join(RESULTS, "cycles_vs_sparsity.csv"), "w") as f:
        f.write("sparsity,mode,nnz,compute_cycles\n")
        for s, m, n, c in cycle_rows:
            f.write(f"{s},{'skip' if m else 'dense'},{n},{c}\n")
    dut._log.info("SparseMAC cocotb regression PASSED")
