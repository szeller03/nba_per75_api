# Big Board architecture — Website152

The known-good Big Board remains the source of ranking values and percentiles:
`load_canonical_percentiles()`.

Basketball-Reference-style minimums are a separate eligibility gate only.
They are evaluated from the season master and matched back to canonical
player-season rows by player ID/season, or normalized player name/season.

The gate never replaces the canonical `Value` column. In particular:
- PTS/75 remains PTS/75; BRef's PTS/PPG minimum is eligibility only.
- Per-75 values are not recomputed by the qualification gate.
- Percentile values remain attached to the canonical row.
- Historical scope keeps qualifying player-seasons without player deduplication.

The existing Big Board ranking/population code was retained as the baseline;
the new code only filters canonical rows after the requested statistic is
selected.
