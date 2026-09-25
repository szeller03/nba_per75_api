# V15 — All Seasons Single-Season Big Board + Raw Values Fix

Added:
- All Seasons filter for an all-time single-season leaderboard.
- All Seasons treats every player-season as a separate leaderboard entry; it does not aggregate careers or deduplicate players.
- Season column added to Big Board rows so all-time single-season entries are identifiable.
- Raw statistic value lookup now keys by player + season + statistic, preventing percentile-only rows from losing their actual value.
- Selected-season boards continue to show one player-season per player.
- Default Dominance Index board remains season-aware.

No source/master analytical data was modified.
