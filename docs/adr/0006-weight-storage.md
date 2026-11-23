# ADR-0006: Flop-array weight storage

**Context:** N x M = 128 INT8 weights. SRAM macro would need modeling
for the open-source flow.
**Decision:** parameterized flop array. Documented tradeoff: SRAM is
future work for larger M (area/power), flop array keeps the Yosys
flow simple and the design fully simulatable.
