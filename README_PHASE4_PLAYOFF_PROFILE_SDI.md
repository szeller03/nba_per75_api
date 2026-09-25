# Phase 4 — Player Profile Playoff SDI Integration

This package fixes the specific issue visible in the Kareem Player Profile
screenshot: playoff statistics load, but the six SDI boxes/spider are NQ/empty.

## What was wrong

The API's `api_profile()` correctly routes Playoffs to `api_playoff_profile()`.
However, the playoff profile response returned playoff statistics and percentiles
without the `category_axes` / SDI fields consumed by the Player Profile's
six-dimension display.

The API also had an authoritative playoff SDI loader pointed at:
`data/precomputed_sdi_v4/playoff_player_season_sdi_v4.csv`
while the Phase-3 rebuild produces:
`local_api/cache/playoff_sdi_v4_player_seasons.csv`.

Phase 4 bridges those layers.

## What Phase 4 adds

- Six playoff `category_axes` to the profile response.
- `SDI_v4_Playoffs`, `SDI_v4`, and `sdi_v4` response fields.
- Season-level lookup prefers the rebuilt Phase-3 playoff SDI cache.
- Career uses the finalized Career playoff percentile family to calculate the
  six category axes and Route-A composite rather than averaging season SDIs.
- Normalizes axis labels to the Player Profile labels:
  Scoring, Efficiency, Creation / Playmaking, Rebounding, Defense,
  Impact / Value.
- Does not re-percentile/re-rank the completed SDI.
- Does not modify regular-season Profile logic.
- Does not modify peak files.

## Apply

Place this package's `local_api` files into your Website241 `local_api` folder,
or run:

```powershell
python local_api\apply_phase4_playoff_profile_sdi.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
python local_api\validate_phase4_playoff_profile_sdi.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
```

Restart the local API after applying.

## About the uploaded JS

`profile_request_manager_reference.js` is included only because it was supplied
with the current build. Its `profileContextKey()` already includes player ID,
season type, season, and percentile context, so Phase 4 does not alter it.

## Important

This package is an API-side integration because the supplied current build
contained the Player Profile API but not the frontend renderer. If the UI still
shows NQ after this API returns non-null `category_axes`/`sdi_v4`, the remaining
piece will be the frontend renderer's field mapping, and the next file needed
will be the Player Profile frontend JS.
