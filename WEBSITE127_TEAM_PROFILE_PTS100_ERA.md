# Website127 — Team Profile, PTS/100, Era Filter

- Fixed the Team Profile 500 root cause: the API file contained two functions
  named `api_team_profile`; the later roster-profile definition silently
  overwrote the analytics-profile definition. The roster function is now
  named `api_team_roster_profile`, while `/teams/profile` uses the analytics
  profile.
- PTS/75 has been replaced with PTS/100. Since team ORtg is points per 100
  possessions, Team PTS/100 is exactly team ORtg.
- Team Profile uses PTS/100 as well.
- Added an Era filter to Team Analytics.
- Era filtering happens server-side, so leaderboard rankings and qualified
  team-season counts are based only on the selected era.
- Existing sorting defaults and dark filters remain intact.
