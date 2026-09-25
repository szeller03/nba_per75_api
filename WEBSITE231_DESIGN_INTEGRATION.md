# Website231 — Prototype-to-Production Integration

This build uses Website230 as the production foundation: existing API contracts, historical data layers, profile logic, comparison logic, Explorer, Teams, and the pairwise Create Your T75 algorithm are retained.

The finalized prototype direction is being integrated into the production React application. The first integration pass is intentionally scoped around the finalized Player Profile and Big Board direction while leaving the other production functionality intact.

## Player Profiles
- Darker card-like presentation.
- Wider profile composition with the spider visually reserved at the top-right.
- Existing canonical profile/season/percentile data remains the source of truth.
- Existing Website230 configurable spider request path is retained.

## Big Board
- Existing Big Board API/data layer remains the source of truth.
- Companion statistics are fetched through the same Big Board endpoint rather than fabricated locally.
- Secondary values are visually smaller, range-graded, and have no percentile beneath them.

## Run
1. Install dependencies with `npm install`.
2. Start the frontend with `npm run dev`.
3. Start the existing local API in `local_api/nba_per75_local_api.py` as required by Website230.
