# NBA PER-75 — Playoff 5-Year Peak V2

This version fixes the performance/availability problem in the playoff
5-Year Peak path.

## What changed

The playoff 5-Year Peak population is now calculated ONCE and written to:

`local_api/cache/playoff_peak_v2.json`

The API loads that precomputed population instead of recalculating the entire
league every time a diagnostic or player profile request is made.

The cached population contains:
- selected five-appearance window
- playoff SDI
- SDI percentile
- all 46 aggregated playoff statistics
- Peak-context percentile for each statistic

The selection rules remain:
- five consecutive playoff appearances
- every appearance >= 3 games and >= 75 minutes
- five appearances total >= 35 games
- highest average season-level playoff SDI selects the window

Regular-season statistics are never substituted for playoff statistics.

## Build the cache

From the Website74 directory:

`python local_api\build_playoff_peak_cache_v2.py`

The script uses the existing NBA_Per75 project at:

`C:\Users\szell\OneDrive\Desktop\NBA_Per75`

or the `NBA_PER75_ROOT` environment variable.

Only after the script reports a non-zero player count should the local API
be started.

## Run

Terminal 1:

`python local_api\nba_per75_local_api.py`

Terminal 2:

`npm install`

`npm run dev`
