# Phase 5A — Playoff Profile Request Deduplication

Built from the known-good Phase 4 V4 profile state package.

## Only change
`src/api.js` now deduplicates identical in-flight Playoff profile requests using the exact context:
- Player ID
- Season Type
- Season
- Percentile Context

If the UI asks for the same Playoff Career profile multiple times while a request is already in flight, all callers share the same Promise and only one `/profile` request reaches the API.

## Deliberately untouched
- `local_api/nba_per75_local_api.py`
- all headshot assets and mappings
- Playoff percentile calculations
- Playoff SDI
- Playoff 5-Year Peak
- Regular Season API/data behavior
- Player Profile rendering/state logic

The existing request-id logic in `App.jsx` remains in place so stale responses cannot overwrite the active context.

## Install
Copy `src/api.js` from this package into your Website241 `src` folder. The included `src/App.jsx` is the unchanged Phase 4 V4 copy for reference/rollback consistency; it does not need to be replaced if your current App.jsx is already Phase 4 V4.

## Expected API-log improvement
For a single Playoff Career context, repeated identical lines such as:
`GET /api/v1/players/.../profile?...season_type=Playoffs&season=Career...`
should collapse to one request while that request is in flight.
