# NBA PER-75 Website V42 — Final Playoff/Big Board/Profile Fixes

V42 addresses the remaining integration problems without rebuilding the authoritative playoff datasets.

## Playoff value source
The API uses the finalized 46-stat playoff layer, but authoritative existing Per-75 fields from `nba_per75_master_v46.csv` take precedence for the 17 Per-75 statistics. This prevents a reconstructed possession denominator from inflating playoff rates.

Playoff career Per-75 values are reconstructed from career total points divided by career estimated possessions, with estimated possessions derived from authoritative PTS/Per-75 when explicit possession totals are unavailable.

## Career Big Board
Regular-season Career now uses a true career aggregation from the canonical regular-season master. Per-75 rates are possession-weighted, additive value stats are summed, and career percentile qualification is G >= 50 and MP >= 1,500.

## Player navigation
- Big Board player rows use canonical `player_id`.
- API route decoding now handles encoded IDs/names.
- Players search is now a live API-backed search with clickable profile results.

## Run
API:
```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website42\nba_per75_website_v42\local_api"
python nba_per75_local_api.py
```
Website in another PowerShell:
```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website42\nba_per75_website_v42"
npm install
npm run dev
```

The production data remains in `C:\Users\szell\OneDrive\Desktop\NBA_Per75`.
