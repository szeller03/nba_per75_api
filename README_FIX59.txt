FIX59 — 5-Year Peak SDI Profile Display Repair

Based on FIX58 (known-good regular-season/playoff SDI display baseline).

Changes are limited to the missing 5-Year Peak Profile axes:
- Regular 5-Year Peak reads the canonical peak's exact five seasons and the canonical season-level raw SDI category layer, then exposes category percentiles to the Profile.
- Playoff 5-Year Peak uses the canonical playoff peak seasons and playoff SDI category layer, with legacy fallback retained.
- Profile continues to display percentile only; raw SDI remains in the data/API/Big Board.

No headshots, statistical source values, formulas, weights, or regular-season/playoff non-peak paths were changed.
