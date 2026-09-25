# V26 — Playoff Statistical Layer

V26 converts the verified V25 playoff identity layer into actual statistical
rate data.

The methodology follows the project's established Basketball-Reference
historical PER-75 pipeline:

- 1952-1973: player totals + playoff Team Pace -> estimated possessions ->
  Per-100 -> Per-75.
- 1974-2026: Basketball-Reference playoff Per-100 tables -> Per-75.
- Per-75 is Per-100 multiplied by 0.75.
- Basic shooting percentages and TS% are recalculated from raw totals.
- Missing source statistics remain missing.

The identity layer is read-only. V26 does not resolve the 259 ambiguous or
289 unmatched identities.

Outputs:
- `nba_per75_playoffs_stats_v1.csv`
- `nba_per75_playoffs_stats_build_audit_v1.csv`

This is the raw/statistical playoff layer. Playoff percentile qualification,
career aggregation, Six Dimension weighting, and UI integration are intentionally
separate later steps.
