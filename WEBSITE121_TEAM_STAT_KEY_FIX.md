# Website121 — Team Statistic Key Fix

The reason Website120 could still show 0 qualified team-seasons was found in
the API itself.

The Team Analytics registry uses display keys such as:
- rDRtg
- rORtg
- NRtg
- PTS/75
- TS%

But the cache builder stores normalized row keys:
- rdrtg
- rortg
- nrtg
- pts75
- tspct

The API was filtering with the display key directly (`r.get("rDRtg")`), which
returns None even when `r["rdrtg"]` exists. That produced an empty leaderboard.

Website121 maps the public selector key to the actual cache key before
filtering/sorting. No team statistics are fabricated or changed.
