# Website162 — Root-cause Player Profile repair

## 5-Year Peak
The previous build did not actually eliminate the expensive operation when the
precomputed regular-peak file was absent. It could still read the entire
dominance dataset during a profile request.

This build:
- Creates a persistent slim `data/cache/profile_dominance_index_v1.csv`.
- Reads only Player_ID/name, season, and SDI from the large dominance source.
- Converts the season to a numeric year once.
- Reuses that compact index for all future peak requests.
- Caches each completed player's regular 5-Year Peak response, so the profile,
  spider, and related requests cannot recompute the same window.
- Keeps the existing precomputed peak JSON fast path when that file exists.

## Duplicate identities
The canonical identity registry now also collapses same-name source IDs when
exactly one of those IDs has authoritative player-season records in the master
table. This catches stale duplicate IDs such as the duplicate Michael Jordan
profiles while retaining genuine namesakes when multiple IDs have real,
distinct season histories.
