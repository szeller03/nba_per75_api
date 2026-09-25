# Website174 — Team master path integration

This continues the existing website-build process. It does not create a new
website project architecture.

Team data is now sourced from the user's actual external NBA_Per75 project:

    NBA_Per75/data/nba_per75_team_master.csv

The optional enriched filename is also recognized:

    NBA_Per75/data/nba_per75_team_master_enriched.csv

The environment variable `NBA_PER75_ROOT` can explicitly point the API to the
NBA_Per75 project root when the two projects are not sibling directories.

The Team analytics cache schema is bumped to v11.

All existing Team statistics remain on the same pipeline. The new master can
contain:
- Opponent_TOV%
- Opponent_eFG%
- Logo_ID
- Logo_File
- Logo_Source

No temporary `team_data` directory is required.
