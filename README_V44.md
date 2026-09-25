# NBA PER-75 Website V44 — Runtime Data-Path Fix

V44 fixes the V43 runtime failure where filters, statistics, player search,
and profiles could return HTTP 500.

## Root cause
V43 had brittle `PATHS` definitions and one stale registry key (`stat_registry`).
The API could therefore fail before the requested page was rendered.

## Fix
The API now:
- discovers the finalized data directories/files under `NBA_Per75`;
- prefers `nba_per75_master_v46.csv` when present;
- falls back to `nba_per75_master_dreb_v2.csv` only if necessary;
- dynamically resolves the player identity, taxonomy, qualification, and
  percentile directories;
- aliases `stat_registry` to the canonical `statistic_registry` path;
- safely falls back to the 46-stat contract if the optional registry file is
  absent;
- exposes `/api/v1/diagnostics` to verify the resolved data paths.

The V43 statistic/career architecture remains intact.

## Test

Start the API:

```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website44\nba_per75_website_v44\local_api"
python nba_per75_local_api.py
```

Then open:

```text
http://127.0.0.1:8000/api/v1/diagnostics
```

Every required data path should report `"exists": true`.

Then start Vite:

```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website44\nba_per75_website_v44"
npm install
npm run dev
```
