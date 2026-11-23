# ADR-0004: Derived accumulator width

**Context:** Signed 8x8 products summed up to M times must never overflow.
**Decision:** `ACC_W = 2*DATA_W + $clog2(M)` (21 bits for M=32).
A product needs 16 bits; summing M products adds ceil(log2 M) bits.
Overflow is impossible by construction; no saturation logic.
