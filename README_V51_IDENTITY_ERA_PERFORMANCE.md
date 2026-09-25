# NBA PER-75 Website V51 — Canonical Identity & Era Performance Repair

- Legacy/source player IDs now resolve to the same canonical public identity.
- Duplicate identities such as Michael Jordan / Michael Jordan* are collapsed to one profile, including stale bookmarks that use the legacy source ID.
- Player search has a second public-key deduplication guard.
- Regular and playoff profile/spider/context endpoints use canonical identity resolution.
- Playoff source matching strips legacy asterisks and falls back from canonical ID to cleaned player name, so playoff career/spider data remains attached to the canonical profile.
- Era Average calculation filters the source to the selected era before row-level era mapping, reducing transition latency while preserving existing result/percentile caches.
- V50 public-facing asterisk removal is preserved.
- Statistical Dominance Index remains deferred.

## Era Average thresholds
- Regular Season: >=40% participation, >=250 games, >=6,000 minutes.
- Playoffs: >=40% participation, >=40 games, >=1,250 minutes.
