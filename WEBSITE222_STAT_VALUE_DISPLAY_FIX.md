# Website222 — Canonical Season Stat Value Display Fix

The profile selector and percentile rows were working, but the individual
season table could show all 46 statistic names with blank raw values while
percentiles were present.

The API was already returning the correct raw `statistic_values`. The remaining
risk was frontend key matching between the canonical registry and the value
payload.

This build:
- Keeps the canonical 46-stat registry as the display universe.
- Adds a normalized statistic-value map to the API payload.
- Makes the frontend resolve each registry statistic against the exact value
  key first, then a normalized alias.
- Percentile rows remain independent; a missing percentile cannot remove a raw
  statistic.
- No values are fabricated. A dash is shown only when the canonical source has
  no value for that statistic/season.

Verified:
- Jokic 2024-25: 46/46 raw values, 46 percentile rows.
- Michael Jordan 1984-85: 46/46 raw values, 46 percentile rows.
- LeBron James 2003-04: 46/46 raw values, 46 percentile rows.
- API syntax/import passes.
