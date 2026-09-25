# PLAYOFF PROFILE STATE FIX — PHASE 4 V4

This package fixes the Playoffs Player Profile state/qualification path.

## What changed
- Playoff single-season percentile qualification is locked to **G >= 4 and MP >= 75**.
- Playoff Career qualification is **G >= 50 and MP >= 1,500**.
- The Player Profile NQ display now uses the correct threshold for the selected season type.
- Playoff profile responses explicitly carry `request_season_type`, `response_season_type`, and `context_key`.
- Playoff profile responses now include six-dimension Route-A category axes and `sdi_v4`/`SDI_v4`.
- Percentile rows expose compatibility aliases (`Percentile`, `percentile`, `Pctl`, `pctl`, `Percentile_Value`).
- Added a dedicated Playoffs season-bundles response so the profile season table no longer calls the regular-season-only public SQLite layer for Playoffs.
- Frontend clears prior profile/table state on context switches and rejects stale Regular Season payloads when the requested context is Playoffs, and vice versa.
- Existing canonical playoff 5-Year Peak path is untouched.

## Files
- `local_api/nba_per75_local_api.py`
- `src/App.jsx`
- `src/api.js` (included unchanged so the overlay is self-contained)

## Install
Copy these files over the matching files in your Website240-derived project. The API file can be replaced after stopping the running Python API.

Start API:
`python local_api/nba_per75_local_api.py`

Then rebuild/restart the frontend.

## Expected result
Selecting **PLAYOFFS** should keep the profile in playoff context for Career and individual seasons. Kareem and other qualifying playoff careers should no longer show NQ merely because the regular-season 400/10,000 threshold was applied. Individual playoff seasons should populate their values, percentiles, and six-dimension axes from the canonical playoff layer.
