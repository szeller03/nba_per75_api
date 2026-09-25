# NBA PER-75 Website76

This version fixes the remaining Playoff 5-Year Peak latency/data-path issue.

## Changes
- Precomputed playoff peak percentile maps are hydrated from the cached 5-Year Peak rows.
- If an older cache lacks percentile maps, the API adds them using only the cached population (no full playoff-season rebuild).
- The playoff 5-Year Peak profile response now bundles its spider payload.
- React uses that bundled spider for Playoffs → 5-Year Peak, avoiding a second expensive request.
- Regular-season and other profile views remain unchanged.

## Existing cache
If you already have:
`local_api/cache/playoff_peak_v2.json`

run:
`python local_api/repair_playoff_peak_percentiles_v1.py`

Otherwise build the cache normally with:
`python local_api/build_playoff_peak_cache_v2.py`
