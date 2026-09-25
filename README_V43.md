# NBA PER-75 Website V43 — Canonical Statistics / Career / Profile Fix

V43 is an integration correction build. It does not rebuild the underlying
playoff datasets.

## Core rule

There is now one canonical displayed 46-stat profile table.

### Playoffs
`nba_per75_master_v46.csv` is authoritative for every statistic it contains,
including all 17 Per-75 statistics. The finalized playoff 46-stat expansion is
used only to fill fields genuinely absent from the master.

This prevents a duplicated/reconstructed possession denominator from replacing
validated Per-75 values.

The validated 2025-26 LeBron playoff source row contains:
`PTS_per75 = 23.40`.

### Playoff career
Career playoff values are rebuilt from the corrected playoff player-season
layer:
- Per-75: estimated-possession weighted
- WS / OWS / DWS / VORP: additive
- percentage statistics: natural-denominator weighted when available
- other rate/index statistics: MP-weighted
- no averaging of season percentiles
- the old playoff career 46-stat file is not used as the raw-value authority

### Regular-season career
Career profile values and the Career Big Board use the canonical regular-season
career aggregation table:
- Per-75: possession weighted
- additive value statistics: summed
- percentage/rate/index statistics: appropriately weighted
- career percentile qualification remains G >= 50 and MP >= 1,500

### Player profiles
- Search routes by canonical player name.
- API can resolve either player ID or exact player name.
- Master-data fallback prevents stale identity-registry mappings from making a
  valid player inaccessible.
- Removed the duplicate second 46-stat table.
- One displayed 46-stat table contains the raw value and its percentile.

### Big Board
- Playoff raw values use the corrected canonical season layer.
- Playoff percentile joins use exact player name + season when IDs differ.
- Career playoff and regular-season boards use corrected career tables.

## Verification
The package passes static integration checks:
- Python syntax
- one 46-stat profile table
- player search routing
- corrected playoff Big Board source
- playoff career source isolation
- regular career source
- identity fallback
- validated LeBron 2025-26 PTS_per75 = 23.40

## Run
Extract as:
`C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website43`

API:
```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website43\nba_per75_website_v42\local_api"
python nba_per75_local_api.py
```

Website:
```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website43\nba_per75_website_v42"
npm install
npm run dev
```

The production `NBA_Per75\data` directory remains authoritative.
