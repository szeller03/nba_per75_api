# Phase 5 — Playoff Profile Performance (Headshot-Safe Build)

This package is the Phase 5 Playoff Profile performance build applied directly to the Website241 local_api package that contains the existing headshot assets.

## What changed
- Uses the Phase 5 optimized `nba_per75_local_api.py`.
- Preserves the existing Website241 `local_api` contents and cache assets.
- Preserves `cache/headshots_processed/` and all existing headshot-related files.
- No Basketball-Reference JPG replacement layer was added.
- No headshot assets are deleted or renamed by this package.
- NBA CDN headshot behavior remains unchanged.
- Playoff 5-Year Peak cache remains unchanged.

## Install
1. Stop the running API.
2. Back up your current `NBA_Per75_Website241\local_api` folder.
3. Replace the contents of `local_api` with the contents of this package's `local_api` folder.
4. Start:
   `python nba_per75_local_api.py`
5. Wait for the Playoff profile cache warm-up to finish before opening the site.

## Expected startup line
`Playoff profile cache ready:`

The package is intended to be a drop-in backend replacement while retaining the existing headshot assets.
