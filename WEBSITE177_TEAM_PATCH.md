# Website177 — Team opponent statistics + logo repair

Website177 is a corrected continuation of Website176. The previous enrichment helper had two critical implementation errors: it wrote to a different CSV path than the website reads, and several regular expressions were double-escaped, preventing year/team matching. Website177 fixes both.

## Where the Python file goes

`populate_team_data_and_logos.py` belongs in the **website project root**, next to `package.json`, `src/`, `local_api/`, `data/`, and `team_data/`.

Do **not** put it inside `src/` or `local_api/`.

## Run it on Windows

From the Website177 root:

```text
py populate_team_data_and_logos.py
```

Or double-click `RUN_TEAM_ENRICHMENT.bat`.

The script writes the populated master to:

`data/nba_per75_team_master_enriched.csv`

and also synchronizes:

`team_data/nba_per75_team_master.csv`

## What it populates

- `Opponent_TOV%`
- `Opponent_eFG%`
- `Logo_ID`
- `Logo_File`
- logo source metadata
- local historical logo files under `team-logos/`

The opponent-factor source is the Brescou regular-season Four Factors dataset for its covered seasons, with Basketball-Reference Defense Four Factors used as the fallback for seasons outside that bootstrap. The site should never fabricate values when a source is unavailable.

## After enrichment

Restart the local FastAPI service so the Team cache is rebuilt from the newly populated master, then restart Vite.

The frontend already contains the Team controls for Opponent TOV% and Opponent eFG%; the key missing piece was the data actually reaching the canonical CSV that the API reads.
