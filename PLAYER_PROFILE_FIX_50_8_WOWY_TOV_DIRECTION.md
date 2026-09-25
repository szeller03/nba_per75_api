# Player Profile Fix 50.8 — Individual WOWY + TOV Direction

## Changes
- Canonical individual-season WOWY cache is now loaded before the site copy and both are merged, so a stale/incomplete `data/player_wowy_statistics_v1.csv` cannot mask available canonical WOWY rows.
- Existing canonical WOWY rows are injected into regular-season profile bundles as first-class `WOWY_Offense`, `WOWY_Defense`, and `WOWY_Net` values and percentiles.
- Regular-season profile `TOV_per75` and `TOV_pct` percentiles are recomputed once from the compact SQLite season values with **lower-is-better** direction, overriding legacy stored directionality.
- Existing career lower-is-better handling is preserved.
- No WOWY values are invented for seasons absent from the canonical WOWY source. Current canonical layer coverage is preserved; the fix removes wiring/masking losses.
- No SDI weights other than the already locked 60% BLK / 40% STL defensive activity split are changed.
