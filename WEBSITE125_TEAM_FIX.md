# Website125 — Team Remaining Fixes

- Removes trailing `*` from team display names and profile lookup.
- Fixes the Team Profile HTTP 500 caused by an accidental reference to
  `rows` before it was assigned.
- Profile now initializes `all_rows` correctly before filtering.
- Relative DRtg and DRtg automatically default to lowest-to-highest.
- PTS/75 remains sourced from the genuine team dataset; no player-level
  aggregation is used to invent a team PTS/75.
