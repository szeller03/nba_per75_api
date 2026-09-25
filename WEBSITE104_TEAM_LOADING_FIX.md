# NBA PER-75 Website104 — Team Database Loading Fix

The Team page was reading the entire canonical master statistics CSV on every
initial team-index request. That file is intentionally large, so this was an
unnecessary bottleneck.

Website104 changes the Team API to:
- Inspect only the master CSV header first.
- Determine the actual team/season/player columns.
- Reload the master with pandas `usecols`, retaining only the columns required
  for the Team page.
- Cache that compact source for subsequent requests.
- Build the team index with a pandas groupby rather than repeatedly converting
  and aggregating full statistic rows.
- Reuse the compact source for team-season detail requests.

No team data definitions were changed. The fix is performance-only.
