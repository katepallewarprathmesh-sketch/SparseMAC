# ADR-0002: Bitmap + packed nonzeros sparse format

**Context:** The encoder must turn a dense x stream into something the
scheduler can drain at 1 issue/cycle with predictable timing.
**Options:** run-length, bitmap, coordinate list.
**Decision:** bitmap + packed nonzeros. Fixed-width bitmap makes the
scheduler a priority encoder; run-length decode has variable latency.
