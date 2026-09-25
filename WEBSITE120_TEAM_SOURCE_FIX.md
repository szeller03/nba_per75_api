# Website120 — Team Analytics Data Source Fix

Website119 successfully fixed the Teams page JSX, but the Team Analytics
leaderboard returned 0 qualified team-seasons because its backend source
discovery was too restrictive.

The old discovery searched recursively for CSV filenames containing "team".
The canonical project data is resolved through PATHS["master"], so the
analytics builder could miss the actual master even when it was present.

Website120:
- checks the resolved canonical master first;
- checks CSV, XLSX and Parquet sources by columns rather than filename;
- requires Team + Season and actual efficiency/rating inputs;
- invalidates the old version-1 analytics cache;
- returns an explicit API error instead of silently presenting zero rows;
- respects season_type when a typed cache exists.

This does not invent team metrics. It uses an actual team-season data source
if one exists. If the master lacks the required team metrics, the page will
now display that exact missing-data reason instead of misleading "0".
