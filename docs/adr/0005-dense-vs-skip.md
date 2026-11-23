# ADR-0005: One RTL, CSR mode (not two designs)

**Context:** The A/B comparison must be fair: same lanes, same weights,
same synthesis settings; only scheduler policy differs.
**Decision:** single RTL with `csr_mode`. Area is identical by
construction; the measured difference is cycles + activity.
