"""Run generic synthesis and summarize measured paired cycle samples.

The optional energy table is an analytical scenario, not an RTL toggle
measurement: its activity factors and overhead are explicit assumptions.
Yosys must exit successfully and produce a nonzero cell count before any
result files are replaced.
"""
import csv
import json
import os
import re
import statistics
import subprocess
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")
RAW_CSV = os.path.join(RESULTS, "cycle_samples.csv")
M = 32
SWEEP_NNZ = (32, 24, 16, 8, 2, 1, 0)
VECTORS_PER_POINT = 16
E_MAC = 1.0       # assumed normalized energy per issue
E_ENC = 2.0       # assumed fixed skip-mode overhead per vector
P_LEAK = 0.05     # assumed normalized leakage power


def atomic_json(path, obj):
    fd, tmp = tempfile.mkstemp(prefix=".ppa-", dir=RESULTS, text=True)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# Synthesis first. A parser/version failure raises before any committed result
# file is touched, and invalid/missing cell counts are treated as hard errors.
yosys_version_run = subprocess.run(
    ["yosys", "-V"], text=True, capture_output=True, check=True)
yosys_version = (yosys_version_run.stdout or yosys_version_run.stderr).strip()
cmd = [
    "yosys", "-p",
    f"read_verilog -sv {ROOT}/rtl/sparsemac.sv {ROOT}/rtl/sparse_scheduler.sv; "
    "synth -top sparsemac; stat",
]
ys = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True)
stat_out = ys.stdout + ys.stderr
cell_matches = re.findall(r"Number of cells:\s+(\d+)", stat_out)
if not cell_matches or int(cell_matches[-1]) <= 0:
    raise RuntimeError("Yosys completed without a valid nonzero generic cell count")
cells = int(cell_matches[-1])

# Raw samples are emitted by the cocotb test. Validate pairing and exact nnz
# before calculating mean and sample standard deviation.
with open(RAW_CSV, newline="") as f:
    raw = list(csv.DictReader(f))
if not raw:
    raise RuntimeError(f"No cycle samples found in {RAW_CSV}; run make test first")

samples = {}
pair_identity = {}
for row in raw:
    target_nnz = int(row["target_nnz"])
    actual_nnz = int(row["actual_nnz"])
    trial = int(row["trial"])
    mode = row["mode"]
    cycles = int(row["compute_cycles"])
    if actual_nnz != target_nnz:
        raise RuntimeError(f"Non-exact vector: target {target_nnz}, actual {actual_nnz}")
    if mode not in ("dense", "skip"):
        raise RuntimeError(f"Unexpected mode {mode!r}")
    key = (target_nnz, trial)
    identity = (actual_nnz, row["vector_sha256"])
    old_identity = pair_identity.setdefault(key, identity)
    if old_identity != identity:
        raise RuntimeError(f"Paired modes used different vectors for {key}")
    point_samples = samples.setdefault((target_nnz, mode), {})
    if trial in point_samples:
        raise RuntimeError(f"Duplicate sample for nnz={target_nnz}, mode={mode}, trial={trial}")
    point_samples[trial] = cycles

if set(n for n, _mode in samples) != set(SWEEP_NNZ):
    raise RuntimeError(f"Expected exact nnz sweep points {SWEEP_NNZ}")
if len(pair_identity) != len(SWEEP_NNZ) * VECTORS_PER_POINT:
    raise RuntimeError("Unexpected number of unique paired vector identities")
expected_trials = set(range(VECTORS_PER_POINT))
for target_nnz in SWEEP_NNZ:
    for mode in ("dense", "skip"):
        if (target_nnz, mode) not in samples:
            raise RuntimeError(f"Missing {mode} samples for nnz={target_nnz}")
        if set(samples[(target_nnz, mode)]) != expected_trials:
            raise RuntimeError(f"Expected exactly {VECTORS_PER_POINT} trials for nnz={target_nnz}, mode={mode}")

summary_rows = []
model_rows = []
for target_nnz in sorted({n for n, _ in samples}, reverse=True):
    sparsity = (M - target_nnz) / M
    mode_means = {}
    for mode in ("dense", "skip"):
        values = list(samples[(target_nnz, mode)].values())
        mean_cycles = statistics.mean(values)
        stdev_cycles = statistics.stdev(values)
        mode_means[mode] = mean_cycles
        summary_rows.append({
            "zero_count": M - target_nnz,
            "nnz": target_nnz,
            "sparsity": f"{sparsity:.6f}",
            "mode": mode,
            "vectors": len(values),
            "mean_compute_cycles": f"{mean_cycles:.6f}",
            "stdev_compute_cycles": f"{stdev_cycles:.6f}",
            "min_compute_cycles": min(values),
            "max_compute_cycles": max(values),
        })
        # Analytical scenario only: fixed user-selected assumptions; no RTL
        # signal toggles are read or counted here.
        alpha = 1.0 if mode == "dense" else target_nnz / M
        modeled_power = alpha * E_MAC + P_LEAK
        overhead = 0.0 if mode == "dense" else E_ENC
        model_rows.append({
            "zero_count": M - target_nnz,
            "nnz": target_nnz,
            "sparsity": f"{sparsity:.6f}",
            "mode": mode,
            "vectors": len(values),
            "mean_measured_compute_cycles": f"{mean_cycles:.6f}",
            "assumed_activity_factor": f"{alpha:.6f}",
            "assumed_fixed_overhead": f"{overhead:.6f}",
            "assumed_leak_power": f"{P_LEAK:.6f}",
            "analytical_energy_scenario": f"{modeled_power * mean_cycles + overhead:.6f}",
        })

# All commands and data validation succeeded. Publish outputs only now.
with open(os.path.join(RESULTS, "cycles_vs_sparsity.csv"), "w", newline="") as f:
    fields = list(summary_rows[0])
    w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(summary_rows)
with open(os.path.join(RESULTS, "analytical_energy_model.csv"), "w", newline="") as f:
    fields = list(model_rows[0])
    w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(model_rows)

record = {
    "tool": yosys_version,
    "top": "sparsemac",
    "generic_cell_count": cells,
    "scope": "generic Yosys synthesis; no PDK or physical implementation",
    "energy_status": "analytical scenario only; no RTL toggle counting",
    "energy_assumptions": {
        "E_MAC_normalized_per_issue": E_MAC,
        "E_ENC_normalized_fixed_skip_overhead_per_vector": E_ENC,
        "P_LEAK_normalized": P_LEAK,
        "skip_activity_factor": "nnz / M (assumed, not measured)",
    },
    "cycle_samples": os.path.relpath(RAW_CSV, ROOT),
    "vectors_per_point_per_mode": min(len(v) for v in samples.values()),
}
atomic_json(os.path.join(RESULTS, "ppa.json"), record)
with open(os.path.join(RESULTS, "ppa_summary.txt"), "w") as f:
    f.write(f"Tool: {yosys_version}\n")
    f.write(f"Generic Yosys cells: {cells}\n")
    f.write("Cycle counts are paired cocotb measurements; see cycle_samples.csv and cycles_vs_sparsity.csv.\n")
    f.write("Energy table is an analytical scenario from explicit assumptions; RTL toggles are not measured.\n")

# Plot measured compute cycles, not the analytical energy scenario.
fig, ax = plt.subplots(figsize=(7, 4))
for mode, marker in (("dense", "o"), ("skip", "s")):
    rows = [r for r in summary_rows if r["mode"] == mode]
    xs = [float(r["sparsity"]) for r in rows]
    ys = [float(r["mean_compute_cycles"]) for r in rows]
    errors = [float(r["stdev_compute_cycles"]) for r in rows]
    ax.errorbar(xs, ys, yerr=errors, marker=marker, capsize=3, label=mode)
ax.set_xlabel("Exact fraction of zero elements")
ax.set_ylabel("Compute cycles per vector (mean ± sample SD)")
ax.set_title(f"SparseMAC paired cycle sweep ({len(raw)} measured runs)")
ax.grid(True, alpha=.3)
ax.legend()
fig.tight_layout()
fig.savefig(os.path.join(RESULTS, "cycles_vs_sparsity.png"), dpi=150)
plt.close(fig)
print(json.dumps(record, indent=2))
