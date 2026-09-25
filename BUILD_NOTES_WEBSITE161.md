# Website161 — Player Profile performance + identity consolidation

## Michael Jordan / duplicate profile fix
- Canonical identity registry now detects same-name source IDs whose season
  histories materially overlap (3+ common seasons) and collapses them to the
  preferred canonical ID.
- Distinct same-name players with disjoint careers remain separate. This
  preserves cases such as the two George Kings.
- Player search/profile routing therefore exposes one Michael Jordan profile
  when the source contains duplicate identity IDs for the same career.

## Regular-season 5-Year Peak performance
- If the compact regular-season peak JSON is missing, the API now builds it
  ONCE at API startup and persists it to:
  data/precomputed_5_year_peak/regular_profile_peaks.json
- Subsequent 5-Year Peak profile requests read only the requested player's
  compact JSON record rather than recomputing the five-year window.
- This moves the expensive league-wide work out of the user's click path.
- Once the cache exists, 5-Year Peak should be a fast profile lookup.
- The one-time build occurs before the API starts accepting requests, so users
  should not experience a multi-minute wait after clicking 5-Year Peak.
