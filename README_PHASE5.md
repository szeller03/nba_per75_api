# NBA PER-75 — Playoff Profile Performance Phase 5

## Purpose
This is a targeted performance pass for the now-correct Playoff Player Profile path.

It does **not** rebuild playoff statistics, percentiles, SDI, or the working 5-Year Peak cache.
It preserves the Phase 4 correctness/state fixes and makes the Playoff profile data layers warm at API startup.

## Changes
- Warms canonical Playoff player-season data at startup.
- Warms canonical Playoff career aggregation at startup.
- Warms Playoff season percentile population at startup.
- Warms Playoff career percentile population at startup.
- Caches complete Playoff profile responses by player + view.
- Caches complete Playoff spider responses by player + season + context + requested stats.
- Adds explicit `request_season_type` / `response_season_type` = `Playoffs` to Playoff profile/spider payloads.
- Keeps the Playoff single-season qualification at **G >= 4 AND MP >= 75**.
- Keeps Career Playoff qualification at **G >= 50 AND MP >= 1,500**.
- Leaves the precomputed Playoff 5-Year Peak path untouched.

## Installation
1. Stop the currently running local API window with `Ctrl+C`.
2. Back up your current:
   `NBA_Per75_Website241\local_api\nba_per75_local_api.py`
3. Copy the `nba_per75_local_api.py` in this package into:
   `NBA_Per75_Website241\local_api\`
4. Start normally:
   `python nba_per75_local_api.py`
5. Wait for:
   `Playoff profile cache ready:`
   before testing the Player Profile.

## What the startup log should now show
After the existing Playoff 5-Year Peak warm, you should see:

`Warming Playoff profile season/career/percentile cache...`

followed by:

`Playoff profile cache ready: {'season_rows': ..., 'career_rows': ...}`

The first Playoff profile click should no longer be responsible for building the entire Playoff source/percentile stack.

## Important
This package is backend-only. It does not alter frontend files, headshots, Big Board data, Regular Season calculations, or the Playoff 5-Year Peak cache.
