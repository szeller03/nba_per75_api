# Website131 — Unified Team Database

The Teams page now has one unified Team Database/Leaderboard surface.

Behavior:
- With no franchise search: apply Season Type, Season, Era, Statistic and
  Order, then display only the Top 50 qualified team-seasons.
- With a franchise search: use the exhaustive historical team-season index
  and display every season for the matching franchise, chronologically.
- The selected statistic is displayed when it exists for that team-season;
  unavailable historical statistics remain `—` rather than excluding the
  team-season from the franchise database.
- The underlying database is not split into a separate UI surface.
- 2TM/3TM/4TM/TOT/TOTAL remain excluded.
- Era is passed to both the analytics population and the exhaustive franchise
  database query.
- Qualified count remains distinct from displayed Top-50 count.
