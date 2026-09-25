# Website130 — Exhaustive Team Database

The Team Database is now explicitly separate from qualified Team Analytics.

## Database behavior
- Every actual team-season record from the canonical master is included.
- 2TM/3TM/4TM/TOT/TOTAL aggregate labels are excluded.
- Searching a team returns every season for that team.
- Database results are chronological, oldest -> newest.
- Database count is the number of team-season records, not the number of
  qualified statistics.
- Clicking any database row opens the Team Profile pathway.

## Analytics behavior
The Team Leaderboard remains statistic-qualified. If a statistic is missing
for a historical team-season, that team-season can be absent from that
specific leaderboard. This is intentionally different from the exhaustive
database.

This removes the conceptual problem where the database's size was being
confused with the qualified-statistic population.
