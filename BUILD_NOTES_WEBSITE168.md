# Website168 — Team Opponent TOV% / Opponent eFG% repair

The Teams UI already had the correct statistic keys and formatting. The missing
values were occurring in the backend team-season analytics layer.

Changes:
- Expanded detection of opponent TOV% and opponent eFG% source columns,
  including common Basketball-Reference/export naming variants.
- Added a fuzzy normalized-column fallback for opponent TOV% and opponent eFG%.
- Bumped the team analytics cache schema from v4 to v5 so an old cache with
  missing opponent fields is not reused.
- Added source-column diagnostics to the generated analytics payload.
- The backend continues to use the source's actual opponent values; it does
  NOT substitute the team's own TOV% or eFG% and does not invent opponent
  values.
- Explorer, Player Profiles, duplicate identity, and NEW SDI v4 5-Year Peak
  are unchanged.
