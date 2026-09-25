# Website124 — Team Data Integrity + Relative Pace

The previous Team Analytics implementation was still capable of treating a
player-season master as a team-season source. This is the root cause of
wildly incorrect team values such as a +14.63 NRtg for the 2017-18 Pacers.

Website124 changes the architecture:

- A genuine team-season source is mandatory.
- Player master files are explicitly rejected.
- 2TM/3TM/4TM/TOT/TOTAL records are excluded before aggregation.
- Team NRtg is always ORtg - DRtg from the same team-season record.
- Relative ORtg and Relative DRtg are calculated from the team-season
  population, never player rows.
- Relative Pace is added as a new selectable statistic and is calculated as
  team Pace minus the season team-population mean.
- Regular Season and Playoffs remain separate populations.
- Old team analytics caches are invalid because Website124 requires cache
  version 4.

Important: Website124 intentionally refuses to fabricate team statistics if
the proper team-season source is not present. This is preferable to showing
plausible-looking but incorrect numbers.
