# NBA PER-75 Website85 — Comparison Percentiles + Independent Ranges

## Fixes
1. Comparison percentiles now use the dedicated finalized percentile source
when player-season profile rows do not carry percentile columns.
2. A compatibility fallback uses Era/Historical percentile columns rather than
showing blanks when a Season-prefixed column is unavailable.
3. Player A and Player B now have independent season ranges:
   - Player A start/end
   - Player B start/end
4. Backend `/api/v1/compare` accepts `start_a`, `end_a`, `start_b`, `end_b`.
5. Existing weighted aggregation methodology is preserved.

Example:
Player A: 1990-91 → 1995-96
Player B: 2015-16 → 2020-21
Both can be compared in one result.
