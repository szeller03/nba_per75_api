# NBA PER-75 Website79

## Main fix: startup cache warming

The 27-second Playoffs -> 5-Year Peak latency was caused by the expensive
precomputed-cache load/percentile hydration happening on the first profile
request. The canonical profile function was already using the cache, but the
cache was being hydrated lazily.

Website79 warms that exact cache once when the local API starts.

Result:
- API startup takes the ~27 seconds once.
- The first player profile request does not pay that cost.
- Subsequent player profiles reuse the in-memory cache.
- No peak windows are recalculated per request.
- No regular-season data is substituted.
- Percentiles and spider remain sourced from the canonical playoff peak cache.

Run:
python local_api/nba_per75_local_api.py

Wait for:
"Playoff 5-Year Peak cache ready."

Then use the website.

Optional validation:
python local_api/diagnose_playoff_peak_warm_cache_v1.py
