# Website129 — Team Filter Direction + Opponent Metrics

- Only DRtg and Relative DRtg default to Lowest -> Highest.
- Every other Team statistic defaults to Highest -> Lowest, including the
  newly added opponent statistics.
- Added Opponent TOV% as a Team Analytics statistic.
- Added Opponent eFG% as a Team Analytics statistic.
- Opponent eFG% is marked lower-is-better, while Opponent TOV% is higher-is-
  better for the default leaderboard because forcing turnovers is beneficial.
- Source aliases support common opponent-stat column names. If the actual
  team-season source has those fields, they flow through the leaderboard and
  profile percentile machinery.
