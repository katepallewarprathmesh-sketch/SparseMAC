# Toolchain (pinned)

| Tool | Version | Used for |
|---|---|---|
| Verilator | 5.032 (Debian trixie) | lint + cocotb sim |
| Icarus Verilog | 12.0 | syntax check |
| Yosys | 0.52 | synthesis stat, formal prep |
| SymbiYosys (sby) | git master (YosysHQ/sby) | formal proof |
| z3 | 5.4.1 (pip z3-solver) | SMT solver for sby |
| cocotb | 1.9.2 | Track B testbench |
| Python | 3.13 | golden model, PPA, plots |
| NumPy | 2.3.5 | golden model |
| matplotlib | 3.11.2 | plots |

Not available in this environment (documented, not claimed):
VCS/Questa (Track A UVM), OpenROAD/OpenSTA (signoff PPA).
Power numbers here are a labeled toggle-count proxy.
