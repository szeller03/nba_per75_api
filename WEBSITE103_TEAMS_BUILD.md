# NBA PER-75 Website103 — Team Database

Built the next major placeholder section: Teams.

Features:
- Regular Season / Playoffs selector.
- Historical season filter.
- Team search.
- Historical team-season index.
- Team-season cards.
- Team-season detail panel.
- Roster/player list for the selected team-season.
- Player names in the team roster link directly to existing player profiles.
- Team data is derived from the canonical master dataset rather than a new
  duplicate data source.
- The API dynamically detects the available team/season/player/minutes/points
  columns, so it can tolerate the finalized master schema's naming.
- If the master dataset does not expose a team column, the page reports that
  explicitly rather than inventing team data.

This is a functional Team Database foundation. Team visual identity, logos,
advanced team ratings, team comparisons, and polished team profiles can be
added in a later visual/analytics pass once the canonical team dataset is
available.
