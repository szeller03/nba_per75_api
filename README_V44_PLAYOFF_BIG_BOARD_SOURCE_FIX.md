# V44 — Playoff Big Board Timeout Fix

The playoff CSV was present (10,769 rows), but the Big Board request could
still hang because the endpoint attempted to rebuild the entire 46-stat
playoff percentile cube whenever the precomputed percentile-long CSV was not
found.

V44 now:
- keeps the complete 10,769-row playoff source;
- uses precomputed playoff percentiles when available;
- otherwise computes **only the requested statistic** for the Big Board;
- applies playoff qualification G >= 7 and MP >= 125;
- keeps raw values available for non-qualified seasons;
- avoids rebuilding all 46 statistics for every request.

This makes an explicit request such as:
`Playoffs / 2025-26 / Season / PTS_per75`
responsive.

IMPORTANT: restart the API after replacing the project. The running Python
process will still contain the old endpoint code until restarted.
