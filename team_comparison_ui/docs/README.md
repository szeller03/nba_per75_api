# NBA PER-75 — Team Comparison UI V1

Adds `/compare/teams` to the existing Team system.

The page consumes the established `GET /api/v1/compare/teams` contract with:
`team_a`, `seasons_a`, `team_b`, `seasons_b`, and `statistics`.

Features:
- Independent Team A / Team B season selections
- Multiple selected seasons per team
- Five canonical team statistics
- Directionality-aware comparison
- Overall and statistic-detail views
- Existing team logos
- Responsive editorial UI
- No direct CSV reads
- No frontend recalculation of source ratings

Install the four source files into the existing React `src/` directory and add
`/compare/teams` to the existing router without replacing `/compare`.
