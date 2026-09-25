FIX61 — Playoff 5-Year Peak SDI DISPLAY WIRING FIX

Based on FIX60. Surgical API-only fix; no frontend or SDI formula changes.

Root cause found after FIX60:
- The playoff 5-Year Peak Profile endpoint successfully loaded the precomputed peak cache.
- The percentile-axis helper then bypassed that loader and read PLAYOFF_PEAK_CACHE_PATH directly, assuming the JSON used a `players` array.
- The active precomputed cache loader uses the cache's `rows` array and converts it into the canonical population dictionary.
- Therefore the helper found no target player and returned [] even though the Profile peak itself existed.
- The frontend is intentionally percentile-only, so an empty category_axes array rendered the playoff 5-Year Peak SDI boxes as dashes.

Fix:
- Make _playoff_peak_percentile_axes() reuse _playoff_peak_population(), the same canonical loader already used by the Profile endpoint.
- It now uses the canonical population rows regardless of whether the underlying cache JSON is stored as `rows` or another supported schema.

Preserved:
- No frontend changes.
- No headshot changes.
- No underlying statistic changes.
- No SDI formula changes.
- No peak-window methodology changes.
