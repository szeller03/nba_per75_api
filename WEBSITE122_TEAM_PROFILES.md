# Website122 — Team Values, Profiles, Percentiles, and Multi-Team Cleanup

Fixes:
1. Leaderboard now receives a display-key value on every row, so selected
   statistic values render instead of only team names.
2. All 2TM, 3TM, and 4TM aggregate team rows are excluded from Team Analytics.
3. Clicking a team-season opens a Team Profile card.
4. Team Profile contains all supported team statistics.
5. Each statistic shows Season, Era, and Historical percentile context.
6. Profile scope controls let the user switch Season / Era / Historical.
7. Percentiles are calculated from the same qualified team-season population
   used by Team Analytics and respect higher-is-better vs lower-is-better.
8. Team season profiles are loaded on demand, so the leaderboard remains fast.
