# NBA PER-75 Website V41 — Playoff UI/API Integration Fix

V41 fixes the remaining website integration issues without rebuilding or
altering the authoritative playoff datasets.

## Data sources
The API now uses the finalized playoff 46-stat outputs:
- `data/nba_per75_playoff_46_stats_v1/nba_per75_playoffs_46_stats_v1.csv`
- `data/nba_per75_playoff_46_stats_v1/nba_per75_playoffs_career_46_stats_v1.csv`
- `data/nba_per75_playoff_46_stats_v1/percentiles_v1/playoff_season_46_percentiles_long_v1.csv`
- `data/nba_per75_playoff_46_stats_v1/percentiles_v1/playoff_career_46_percentiles_long_v1.csv`

The authoritative master is no longer re-aggregated for the player profile or
Big Board when the finalized 46-stat layer exists.

## Fixed
- Correct playoff Per-75 values from finalized 46-stat layer.
- Player profiles display all 46 registered playoff statistics when a source
  value exists.
- Non-qualified seasons remain visible with raw statistics; percentile cells
  are blank rather than removing the season.
- Big Board season options come from the complete raw playoff season layer,
  not the qualified percentile population.
- Big Board season options are chronological.
- Big Board explicit-stat rows merge raw values with percentile values.
- Big Board player rows route by canonical `player_id`, with player name as
  fallback.
- Playoff spiders and Context Profile use finalized percentile outputs.
- Custom 46-stat spider respects playoff Season/Era/Historical or Career
  context.
- Career remains a separate scope rather than a Season/Percentile Context
  option.

## Verification
Python API syntax passes static compilation.

Run locally:
```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website40\nba_per75_website_v40"
npm install
npm run dev
```

API:
```powershell
python local_api\nba_per75_local_api.py
```

The production data remains in:
`C:\Users\szell\OneDrive\Desktop\NBA_Per75`
