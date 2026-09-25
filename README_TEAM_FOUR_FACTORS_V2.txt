TEAM FOUR FACTORS V2 REFRESH

Why this exists:
The existing team master has ambiguous/incorrect offensive eFG% and TOV% mappings. The Team Profile screenshot showed Utah 1997-98 using the defensive values for the offensive fields.

Authoritative source:
Basketball-Reference Team Advanced Stats, using the distinct Offense Four Factors and Defense Four Factors columns.

One-time Windows command (from local_api):
python precompute_team_four_factors_v2.py

This creates:
local_api/cache/bref_team_four_factors_v2.json

The API then uses that local cache as the source of truth for:
- eFG%
- TOV%
- Opponent eFG%
- Opponent TOV%

The API does NOT scrape Basketball-Reference on every table/profile request. The scrape is a one-time cache build, so normal Team table/profile requests remain local and fast afterward.

The profile relative-rate fix also converts fraction differences to percentage-point display. Example:
.293 - .202 = .091 -> +9.1%

Relative Pace remains a numeric rating-point difference, not a percentage.


REFRESH FIX (v3 builder):
The first v2 sweep was rate-limited by Basketball-Reference (HTTP 429). v3 adds explicit 429 backoff, a slower request cadence, and resumable caching. Failed requests are NOT written as empty seasons, so rerunning the command will retry them instead of silently treating them as completed. Existing v2 empty entries are discarded once at startup because they may represent failed 429 requests.

Run from local_api:
python precompute_team_four_factors_v2.py

The process may take several minutes because it intentionally spaces requests and backs off when BRef rate-limits the connection. You can safely stop and rerun; completed seasons remain cached.
