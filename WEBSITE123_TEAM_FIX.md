# Website123 Team Correctness Fix

- Stops using the player master as a team analytics source.
- Requires an actual team-season source with Team, Season, ORtg, DRtg and Pace.
- Separates Regular Season and Playoffs using Season Type when available, or
  a playoff/postseason source filename for playoff-only data.
- Hard-excludes 2TM/3TM/4TM before building and again at API output.
- Keeps rORtg/rDRtg/NRtg derived only from actual team ORtg/DRtg.
- Preserves the Team Profile API route.
- Invalidates version-2 team caches in favor of version 3.
