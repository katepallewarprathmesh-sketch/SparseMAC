# ADR-0003: Find-first-set scheduler

**Context:** A sequential scan wastes cycles on zero runs, defeating
the purpose of skipping.
**Decision:** find-first-set + clear lowest bit: constant 1 issue/cycle
regardless of zero runs. The FFS over M bits is the likely critical
path; pipelining it (one extra stage) is the documented design-space
point. Formally proven (P1/P2a/P2b, k-induction).
