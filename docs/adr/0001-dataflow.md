# ADR-0001: Column-broadcast dataflow

**Context:** `y = W x` with activation sparsity. Skipping must skip
*columns* of work, not individual products.
**Options:** (a) row-wise dot product - each row scans x independently,
needs per-row skip logic; (b) column broadcast - for each issued column
`j`, all lanes do `acc[i] += W[i][j]*x[j]`.
**Decision:** (b) column broadcast. One scheduler decision skips an
entire column. Cost: weights are read by column (flop array, ADR-0006).
