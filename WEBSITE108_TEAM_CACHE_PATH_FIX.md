# NBA PER-75 Website108 — Team Cache Path Fix

Root cause of the indefinite Team loading:

The API's canonical data root is intentionally the established
`C:\Users\szell\OneDrive\Desktop\NBA_Per75` directory. Website107 accidentally
used that ROOT for `TEAM_INDEX_CACHE` too. Therefore the copied website was
looking for its generated team cache in the established data project rather
than in its own `local_api/cache` directory.

The precompute script also used a different root-resolution rule.

Website108 fixes both sides:
- Canonical master data continues to come from the established NBA_Per75 data
  root.
- `team_index_v1.json` and `team_rosters_v1.json` are ALWAYS written beside the
  website's own `local_api` directory.
- API and precompute script now use the same canonical-root resolution.
- The frontend now reports an explicit timeout/error instead of remaining in
  the generic loading state indefinitely.

This is the first build where the Team cache location is consistent between
the API, precompute script, and frontend.
