# NBA PER-75 — Explorer Fix 49

This is an isolated follow-up to Explorer Fix 48, preserving the Fix46 performance baseline and the Explorer primary-X population model.

## Fixes
- Restores a working season selector for Single Season Explorer using the indexed percentile season list.
- Fixes the indexed Explorer SQL to match the actual public percentile schema (the percentile table does not contain a season_type column).
- Keeps X as the dominant/primary ranking variable; Y only describes those same X-ranked observations.
- Keeps T25/T50/T100 only, with T100 as the default; no All option.
- Keeps X/Y range filters.
- Prevents range inputs from overflowing the controls panel.
- Makes the scatter chart stretch to the same grid-row height as the controls panel, so its bottom aligns just above Distribution.
- Adds a small population status line and an explicit empty-state message.

## Preserved
- Player Profile performance lock.
- Player Comparison performance optimization.
- Big Board Fix45 path.
- SDI v4 / WOWY architecture and weights.
- Existing headshot system.
- Existing Explorer UI and non-indexed fallback behavior for views not supported by the compact indexed layer.

## Important
No generated public SQLite databases are replaced by this source patch. Merge the included source files into the current Website240/Fix46-derived project and rebuild the frontend as usual.
