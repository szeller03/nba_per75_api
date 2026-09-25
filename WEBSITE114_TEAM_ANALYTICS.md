# Website114 — Team Analytics + Leaderboard

Replaces the basic Team roster index view with the intended Team Analytics
foundation.

Frontend:
- Customizable statistic selector.
- Highest / Lowest sorting.
- Season Type selector.
- Season selector.
- Team search.
- Ranked team-season leaderboard.
- Secondary rDRtg/rORtg/NRtg/Pace values on every row.
- Summary cards for rDRtg, rORtg, NRtg and Pace.

Primary supported metrics:
rDRtg, rORtg, NRtg, Pace, ORtg, DRtg, PTS/75, TS%, eFG%, 3PAr, TOV%, ORB%, FTr.

Backend:
- `/api/v1/teams/analytics`
- Dedicated compact analytics cache.
- Prefers a canonical team-season CSV containing actual team metrics.
- Derives NRtg = ORtg - DRtg if absent.
- Derives rORtg = team ORtg - season team mean if absent.
- Derives rDRtg = team DRtg - season team mean if absent.
- Does not fabricate playoff rows if the canonical source does not contain
  playoff team seasons.

One-time precompute:
python local_api\precompute_team_analytics_v1.py

The next stage can add full Team Profiles, team percentile rankings, franchise
rollups, and team-vs-team comparisons on this canonical team analytics layer.
