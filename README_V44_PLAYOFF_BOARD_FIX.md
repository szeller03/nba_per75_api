# V44 — Playoff Big Board Source Fix

The playoff Big Board was failing because the API could see the playoff parent
directory but its CSV resolver could not reliably locate the finalized
`nba_per75_playoffs_46_stats_v1.csv` output inside copied/nested data folders.

The loader now:
1. searches the playoff 46-stat directory recursively;
2. checks the exact finalized season/career filenames;
3. falls back to an exact recursive search under `NBA_Per75\data`.

The regular-season endpoints are unchanged.

After starting the API, this should now return rows:
`/api/v1/big-board?season_type=Playoffs&season=2025-26&context=Season&statistic=PTS_per75&sort=desc&limit=10&scope=single`

Before testing the UI, you can verify the source with:
```powershell
python -c "import sys; sys.path.insert(0,'.'); import nba_per75_local_api as a; x=a._load_final_playoff_46_file(False); print('PLAYOFF ROWS:',len(x)); print('COLUMNS:',list(x.columns)[:20])"
```
Run that from the `local_api` directory.
