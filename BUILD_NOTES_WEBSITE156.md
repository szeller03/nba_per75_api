# Website156 — AST:TOV + duplicate identity repair

## Fixes
- Big Board single-season AST:TOV is now built directly from raw regular-season AST and TOV totals, so it no longer depends on AST_TOV being present in the canonical percentile table.
- A single-season AST:TOV value requires recorded turnovers; seasons without TOV are excluded from that statistic.
- Career AST:TOV only uses seasons ending in 1978 or later (1977-78 onward). Pre-1977-78 assists are never included in the career numerator.
- Career AST:TOV is calculated as total post-1977-78 assists divided by total post-1977-78 turnovers, not an average of season ratios.
- Distinct players with identical names are no longer collapsed into one identity. This specifically prevents the two NBA players named George King from being merged.
- Canonical career Player_IDs are preserved when available instead of being remapped by player name.
