Website240 Performance Fix 40 — Stability Restore

Fix 40 deliberately restores the proven Fix 36 backend architecture. Fixes 38/39 introduced a new Big Board cache path that was not yet safe for the complete Website240 response contract and, in Fix 39, removed portions of the Fix 36 Career/curated-player hot paths. This package does NOT carry those regressions forward.

Preserved from Fix 36:
- response-ready Career spider cache
- Career SDI/WOWY axes
- curated player batch endpoint
- season-bundle optimization
- SQLite public-data layer / Fix 32 handling
- SDI v4 and WOWY methodology
- existing peak caches and profile data behavior

Do NOT run the Fix 38/39 Big Board cache builder for this package. We are intentionally returning to the stable backend before measuring the remaining frontend bottleneck.

Start:
  python nba_per75_local_api.py

Then run the existing Fix 36 test if desired:
  python test_fix36_performance.py

Next step after confirming stability: frontend performance audit. The remaining delays seen in the browser log are not explained by the direct API benchmark, so we should not modify backend data delivery again without the frontend source.
