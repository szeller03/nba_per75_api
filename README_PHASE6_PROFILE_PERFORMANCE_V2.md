# Phase 6 V3 — Playoff Individual-Season Percentiles

This is an isolated correction on the Phase 6 V2 profile-performance build.

## Fix
- Restores canonical playoff individual-season percentiles to the fast public season-bundles response.
- Uses the existing corrected playoff percentile layer rather than inventing a second percentile source.
- Corrects playoff single-season qualification to G >= 4 and MP >= 75.
- Warms the corrected playoff percentile cache at API startup so the first profile does not pay the percentile-build cost.
- Preserves the Phase 6 V2 frontend, individual-season persistence, profile prefetch, NQ loading-state fix, SDI/WOWY behavior, and headshot assets.

## Files changed
- `local_api/nba_per75_local_api.py` only for the playoff percentile attachment/warm-up and G>=4 correction.
- Frontend files are unchanged from Phase 6 V2.
- No headshot/data asset files are replaced.
