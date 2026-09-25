# Website240 Performance Layer 29

## What changed

The public hot path now has a precomputed SQLite layer containing:

- 4,896 canonical player index records
- 36,251 indexed player-season payloads
- 1,006,537 percentile observations
- 2,619 team-season records

The large research CSVs remain build-time sources and are not read by the new public endpoints.

## Measured query performance

Direct SQLite-layer timings on the packaged data:

| Query | Time |
|---|---:|
| Player search: Wilt | ~2.8 ms |
| All Wilt regular-season bundles | ~1.1 ms |
| Wilt 1959-60 profile payload | ~0.1 ms |
| 1959-60 PTS/75 Big Board, 100 rows | ~1.0 ms |
| Historical PTS/75 Big Board, 100 rows | ~2.0 ms |
| 1959-60 Teams | ~27.8 ms |

These are application-layer query times before browser/network transfer and JSON serialization.

## Profile improvement

The previous Player Profile implementation requested the season list and then fetched each season individually with up to six concurrent requests. Layer 29 replaces that with one season-bundle request containing all season rows.

## 2PA contract

The public layer preserves the already-fixed behavior:

`2PA/75 = FGA/75` for regular seasons before 1979-80.

The same FGA percentile is used for 2PA/75 when the historical 2PA percentile row is absent.

## Intentionally deferred

- Explorer population-selection algorithm
- route-level JS code splitting
- CDN/edge hosting configuration
- final image format/CDN pass
- Career/Playoff specialized cache migration

Those should be subsequent performance/QA passes rather than mixed into this data-layer build.
