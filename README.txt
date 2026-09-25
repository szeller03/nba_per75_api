NBA PER-75 — Player Profiles v17 isolated fixes

Built directly from the restored v16 baseline.

ONLY isolated Player Profile areas were changed:
1. Individual regular-season SDI category display remains season-relative percentile:
   raw category SDI is ranked within the same season; highest = 100.
2. Career AST:TOV now uses only seasons with recorded turnovers. Seasons without
   recorded TOV are excluded, and multi-team rows are aggregated by season first.
3. Career display is explicitly tied to the active Regular Season / Playoffs context,
   preventing a prior season-type career payload from remaining visible after switching.

No other sections or locked functionality were intentionally modified.

Scope: SRC + Local API — Player Profiles only.

Validation: Local API Python syntax check passed. Full Vite build was not run because
this patch contains only the source/API files from the restored baseline.
