# Website75 — Playoff 5-Year Peak Percentile + Spider Fix

Website75 is based on Website74.

Fixed:
- Playoff 5-Year Peak API now explicitly exposes cached Peak percentile rows.
- SDI Peak percentile is exposed as a percentile row.
- Playoff Peak spider is no longer disabled by the frontend.
- Playoff Peak context profile is no longer suppressed by the frontend.
- Custom-stat spider can request Peak context.
- Six dominance axes use the canonical aggregation specification against the same Peak percentile map.
- Frontend has a direct `peak_percentiles` fallback for displaying percentile values.

The precomputed playoff peak cache remains the source of truth. No regular-season
values are substituted for playoff values and no browser-side recalculation is performed.
