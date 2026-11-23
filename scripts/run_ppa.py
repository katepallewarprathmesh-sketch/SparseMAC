"""PPA + power-vs-sparsity experiment for SparseMAC.

1. Synthesizes the RTL with Yosys (generic synth) and parses `stat`
   for cell count / area proxy. The same RTL serves dense and skip
   (one design, CSR mode - ADR-0005), so area is identical by
   construction; the A/B difference is cycles and activity.
2. Power model (documented proxy, NOT signoff):
   - Measured compute cycles come from results/cycles_vs_sparsity.csv
     (produced by the cocotb regression).
   - Activity factor: dense mode toggles MACs every cycle (alpha=1.0);
     skip mode toggles only on issue cycles (alpha = nnz/M) thanks to
     operand isolation (R7), plus a fixed encoder/scheduler overhead
     per vector (E_enc, in MAC-energy units).
   - P_avg ~ alpha * P_mac + P_leak;  E_vector = P_avg * cycles.
   This is a toggle-count proxy in the spirit of the blueprint's
   fallback ("if OpenSTA activity import fails, fall back to a
   toggle-count proxy and label it clearly"). OpenROAD/OpenSTA are
   not available in this environment, so no signoff power is claimed.
3. Finds the break-even sparsity where skip energy < dense energy.
"""
import csv
import json
import os
import re
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.join(os.path.dirname(__file__), "..")
RESULTS = os.path.join(ROOT, "results")
os.makedirs(RESULTS, exist_ok=True)

# ---- 1. Yosys synthesis stat ----
ys = subprocess.run(
    ["yosys", "-p",
     "read_verilog -sv ../rtl/sparsemac.sv ../rtl/sparse_scheduler.sv; "
     "synth -top sparsemac; stat"],
    cwd=os.path.join(ROOT, "formal"), capture_output=True, text=True)
stat_out = ys.stdout + ys.stderr
cells = None
m = re.search(r"Number of cells:\s+(\d+)", stat_out)
if m:
    cells = int(m.group(1))
print("Yosys cells:", cells)
if cells is None:
    print(stat_out[-2000:])

# ---- 2. Power / energy proxy from measured cycles ----
rows = []
with open(os.path.join(RESULTS, "cycles_vs_sparsity.csv")) as f:
    for r in csv.DictReader(f):
        rows.append((float(r["sparsity"]), r["mode"],
                     int(r["nnz"]), int(r["compute_cycles"])))

M = 32
E_MAC = 1.0      # energy per MAC issue (normalized units)
E_ENC = 2.0      # encoder+scheduler energy per vector (normalized)
P_LEAK = 0.05    # leakage power (normalized)

def energy(mode, nnz, cycles):
    if mode == "dense":
        alpha = 1.0
        e_enc = 0.0
    else:
        alpha = nnz / M  # operand isolation: idle lanes held at zero
        e_enc = E_ENC    # encoder + scheduler overhead per vector
    p_avg = alpha * E_MAC + P_LEAK
    return p_avg * cycles + e_enc, p_avg

out_rows = []
for sparsity, mode, nnz_v, cycles in rows:
    e, p = energy(mode, nnz_v, cycles)
    out_rows.append((sparsity, mode, nnz_v, cycles, round(p, 4), round(e, 4)))

with open(os.path.join(RESULTS, "power_vs_sparsity.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sparsity", "mode", "nnz", "compute_cycles",
                "avg_power_proxy", "energy_per_vector_proxy"])
    w.writerows(out_rows)

# Break-even: interpolate where skip energy crosses dense energy.
dense = {s: e for s, m, n, c, p, e in out_rows if m == "dense"}
skip = {s: e for s, m, n, c, p, e in out_rows if m == "skip"}
common = sorted(set(dense) & set(skip))
breakeven = None
for a, b in zip(common, common[1:]):
    da, db = dense[a] - skip[a], dense[b] - skip[b]
    if da == 0:
        breakeven = a
        break
    if da * db < 0:  # sign change
        breakeven = a + (b - a) * da / (da - db)
        break

ppa = {
    "tool": "Yosys 0.52 generic synth (no PDK; cell count is a proxy)",
    "cells": cells,
    "note": "One RTL for both modes (ADR-0005): area identical by "
            "construction. OpenROAD/OpenSTA not available here; power "
            "is a labeled toggle-count proxy, not signoff.",
    "break_even_sparsity": breakeven,
    "energy_units": "normalized (E_MAC=1 per issue, E_ENC=2/vector)",
}
with open(os.path.join(RESULTS, "ppa.json"), "w") as f:
    json.dump(ppa, f, indent=2)
print("break-even sparsity:", breakeven)

# ---- 3. Plots ----
def plot(col, ylabel, fname, title):
    plt.figure()
    for mode, marker in (("dense", "o"), ("skip", "s")):
        xs = [r[0] for r in out_rows if r[1] == mode]
        ys = [r[col] for r in out_rows if r[1] == mode]
        plt.plot(xs, ys, marker=marker, label=mode)
    if breakeven is not None:
        plt.axvline(breakeven, linestyle="--", color="gray",
                    label=f"break-even ~{breakeven:.2f}")
    plt.xlabel("activation sparsity (fraction zero)")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS, fname), dpi=150)
    plt.close()

plot(3, "compute cycles per vector", "cycles_vs_sparsity.png",
     "SparseMAC: cycles vs sparsity (measured)")
plot(4, "avg power (proxy, normalized)", "power_vs_sparsity.png",
     "SparseMAC: power vs sparsity (toggle-count proxy)")
plot(5, "energy per vector (proxy, normalized)", "energy_vs_sparsity.png",
     "SparseMAC: energy per vector vs sparsity (proxy)")

with open(os.path.join(RESULTS, "ppa_summary.txt"), "w") as f:
    f.write(f"Yosys generic-synth cells: {cells}\n")
    f.write("Modes share one RTL (ADR-0005): area identical by construction.\n")
    f.write(f"Break-even sparsity (energy proxy): {breakeven}\n")
    f.write("Power/energy are toggle-count proxies, NOT signoff. "
            "OpenROAD/OpenSTA unavailable in this environment.\n")
print("PPA done.")
