# WEBSITE288 — Historical Headshot Normalization Fix

## Purpose
Fix presentation of the Basketball-Reference fallback headshots introduced for historical/missing NBA CDN records.

## Changes
- Added server-side normalization in `local_api/nba_per75_local_api.py` for Basketball-Reference image responses.
- Near-white background pixels are removed only when border-connected, preserving white uniforms and internal details.
- Historical fallback photos are tightly cropped to the visible player with a small safety margin.
- Normalized fallback images are cached locally as transparent PNGs under `local_api/cache/headshots_processed/`.
- Frontend identifies API-served fallback images with `headshot-proxy` and uses `object-fit: contain` / bottom-center positioning to avoid aggressive cover crops.
- Existing NBA CDN photos are not processed or replaced by this patch.
- No player statistics, SDI, peak logic, comparison calculations, Explorer population logic, Teams data, or Create Your Top 75 logic was changed.

## Validation
- `python -m py_compile local_api/nba_per75_local_api.py` passed.
- Website ZIP source remains based on Website287.
- A full Vite production build was not claimed because the local dependency tree does not expose an installed `esbuild` binary in this environment.
