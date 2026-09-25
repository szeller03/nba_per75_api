# Website175 — Team master + historical logo wiring

Targeted Team-only build based on Website174.

FIXES:
1. Canonical Team source order is now:
   - NBA_Per75/data/nba_per75_team_master_enriched.csv
   - NBA_Per75/data/nba_per75_team_master.csv
2. Team analytics cache version is corrected/bumped to v12. The previous build
   had a payload/cache-version mismatch.
3. Existing Team fields (TS%, eFG%, 3PAr, TOV%, ORB%, FTr, etc.) are read
   directly from the master CSV.
4. Opponent_TOV% and Opponent_eFG% are read directly from the master CSV.
   They are NOT fabricated from the team's offensive values.
5. Logo_ID / Logo_File / Logo_Source are carried from each team-season master
   row into Team analytics API rows.
6. Teams UI now renders the logo asset when Logo_File points to a real asset,
   and uses a compact initials fallback rather than a broken/empty image frame
   when the asset is absent.

IMPORTANT DATA NOTE:
The current enriched CSV has the two opponent-stat columns but they are blank
until populated from Basketball-Reference's Defense Four Factors. BRef's
Advanced Stats table explicitly separates Offense and Defense Four Factors,
including eFG% and TOV%. See the source page used for the data model.
The historical logo ID is season-specific; SportsLogos.Net documents logo
timelines by historical periods, e.g. Minneapolis Lakers 1947/48–1959/60.
