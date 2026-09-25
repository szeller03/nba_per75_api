# Website242 — SDI v4 Formula Integration

This is a targeted drop-in patch for the Website242 build. It fixes the site continuing to use the retired SDI v4 weighting/cache layer.

## Regular-season SDI v4 (locked)
- Scoring Volume: 22%
- Efficiency: 20%
- Creation / Playmaking: 20%
- Rebounding: 10.5%
- Defense: 22%
- Impact / Value: 5.5%

The regular-season API now uses a new formula-specific cache namespace, so the old `regular_sdi_v4_wowy_rts_player_seasons.csv` cannot silently override the new formula.

## Playoff SDI v4 (locked for no-WOWY playoffs)
Playoff WOWY is unavailable, so Impact / Value (WOWY Net) is removed rather than replaced by a proxy. The removed 5.5% is redistributed proportionally across the remaining five categories:
- Scoring Volume: 23.280423%
- Efficiency: 21.164021%
- Creation / Playmaking: 21.164021%
- Rebounding: 11.111111%
- Defense: 23.280423%

Creation and Defense also remove their unavailable WOWY groups and renormalize their remaining groups.

## Files
- `local_api/nba_per75_local_api.py` — active API formula/cache wiring
- `config/statistical_index_v4_locked.json` — locked formula manifest
- `src/App.jsx` — playoff profile now renders five SDI dimensions instead of displaying retired Impact / Value

## Important
Restart the local API after replacing the file. The old API process can keep the old formula in memory until it is restarted.

Then restart Vite/dev server if the frontend is already running.

## Validation performed
- Python syntax compilation: PASS
- Locked regular formula loader: PASS
- Synthetic all-100 percentile calculation returns SDI = 1.0: PASS
- Frontend JSX was patched without putting CSS into `App.jsx`

The full historical percentile/data layer is intentionally not regenerated in this patch; the API computes the new formula from the existing authoritative data layer and deliberately bypasses the retired regular SDI cache namespace.
