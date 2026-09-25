# NBA PER-75 V46 — Critical Playoff Data Repair

## What this fixes

This repair addresses the two remaining critical issues found in V45:

1. **Wildly inflated playoff Per-75 values.**
   The previous playoff-46 layer was built from a broken player-possession denominator. For example, LeBron James's 2025-26 playoff PTS/75 was reported as 115.62 even though the validated `nba_per75_master_v46.csv` reports 23.4.

2. **Career scope inaccessible for the playoff Big Board.**
   The frontend previously reset Scope to Single Season whenever the dataset changed, and the playoff career percentile path depended on stale/broken percentile files.

## V46 approach

- The website now treats `nba_per75_master_v46.csv` as the authoritative playoff season source.
- Validated playoff Per-75 values are consumed directly from the master rather than reconstructed from `nba_per75_playoffs_stats_v2.csv`.
- Playoff career Per-75 values are calculated using the validated master estimated-player-possession weights.
- Career additive metrics are summed; percentage metrics use their natural attempt denominators; other rate/index metrics use minutes weighting.
- Old playoff-46 percentile CSVs are intentionally ignored and percentiles are recomputed from the corrected season/career layer.
- Career scope is preserved when switching between Regular Season and Playoffs.
- `NBA_PER75_ROOT` may be set as an environment variable for copied installations; otherwise the established Desktop path is used.

## Verified values

Using the supplied NBA_Per75 data:

- LeBron James, 2025-26 Playoffs: **23.4 PTS/75**
- LeBron James, playoff career: **27.3727 PTS/75**
- Playoff Big Board PTS/75 requests return normal values.
- Playoff player profile for LeBron 2026 returns **23.4 PTS/75**.
- Playoff player profile Career returns **27.3727 PTS/75**.

## Files changed

- `local_api/nba_per75_local_api.py`
- `src/App.jsx`

No changes were made to the underlying NBA_Per75 data files.

## Run

Start the API:

```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website46\nba_per75_website_v44_playoff_board_fix\local_api"
python nba_per75_local_api.py
```

Then start the frontend in a second PowerShell window:

```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website46\nba_per75_website_v44_playoff_board_fix"
npm run dev
```

If you are replacing files in the existing V45 project instead of using this extracted folder, replace only the two changed files above.
