# V17 — Canonical Big Board Rebuild

The Big Board no longer depends on the prepared visualization Big Board CSV.
It is built directly from the canonical player-season percentile foundation.

Season selector:
- Historical Percentile · All Seasons — one all-time single-season scope,
  using Historical Percentile.
- One option for every season actually present in the database.
- Conventional YYYY-YY labels are displayed as their ending calendar year,
  e.g. 1951-52 -> 1952 and 2025-26 -> 2026.

Statistic board:
- Raw statistic value and percentile are taken from the exact same
  player-season-statistic source row.
- Historical scope keeps every player-season as a separate observation.
- A specific season shows one row per player for that season.

Default board:
- Statistical Dominance Index remains the default ranking.

No source/master analytical data was modified.
