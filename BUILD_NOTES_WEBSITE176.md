# Website176 — Team opponent-factor completion + bundled Team source + logo fallback

Built directly from Website175.

## Changes

1. Bundles `data/nba_per75_team_master_enriched.csv` with the website so Team analytics no longer depends on an external `NBA_Per75/data` folder when this build is copied.
2. Team analytics cache version bumped from v12 to v13.
3. Opponent TOV% and Opponent eFG% remain first-class Team statistics, with the existing correct leaderboard directions: Opponent TOV% higher is better; Opponent eFG% lower is better.
4. Team profile statistics use the same opponent-stat keys and percentile machinery.
5. Team logos now have a two-stage asset strategy: bundled/local `team-logos/<Logo_ID>.png` when available, then a season-specific fallback to the TGOlson historical-logo repository using `Logo_ID`.
6. The enrichment script was corrected to use the repository's actual historical asset location: `data/img/team/<Logo_ID>.png`.
7. Added a self-contained `populate_team_data_and_logos.py` to populate opponent factors and optionally bundle logo assets when run in an environment with network access.

## Data status

The supplied enriched CSV still has 0 populated values for Opponent_TOV% and Opponent_eFG%. The source for those values is valid and is wired into the enrichment script: Basketball-Reference Team Advanced Stats / Defense Four Factors, with the MIT-licensed Brescou four-factors dataset as a bootstrap for its covered seasons.

The current execution environment could not fetch the external CSV/repository, so Website176 does not fabricate missing opponent values. Run `python populate_team_data_and_logos.py` from the project root on a networked machine to populate them and download local logo binaries.

## Verification

- Opponent-stat mappings and directions remain intact.
- Bundled Team master is preferred by the API.
- API cache version is v13.
- Logo fallback uses the season-specific `Logo_ID`.
