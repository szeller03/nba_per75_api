# Website173 — restore original Team master architecture

This build corrects the Website172 architectural mistake.

## Team master CSV
Created:
`team_data/nba_per75_team_master.csv`

It is based directly on the existing Team master CSV supplied by the user.
All 41 original columns/values are preserved, including:
TS%, eFG%, 3PAr, TOV%, ORB%, FTr, ORtg, DRtg, Pace, etc.

Only two new columns are added:
- Opponent_TOV%
- Opponent_eFG%

They are intentionally blank in this build until the user populates them with
the Basketball-Reference Defense Four Factors. The Basketball-Reference
Advanced Stats table has separate Offense and Defense Four Factors columns,
including eFG% and TOV%. citeturn0search1turn0search0

## API
The API now explicitly prefers:
`team_data/nba_per75_team_master.csv`

It no longer points to the temporary `data/nba_per75_team_master_v2.csv`.
The runtime BRef opponent-stat merge is removed.

The Team analytics cache schema is bumped to v10 so it regenerates against the
restored full master schema.

## Placement
When using the website project, place the supplied CSV at:
`NBA_Per75_Website96/team_data/nba_per75_team_master.csv`

If a file with that exact name already exists there, replace it with this one.

Then populate the two new columns from the actual Defense Four Factors and run
the existing Team precompute process normally. No other Team statistics need
to be re-created or moved.
