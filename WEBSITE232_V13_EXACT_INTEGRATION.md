# NBA PER-75 Website232 — v13 Exact Visual Integration

This revision uses Website230 as the functional/data foundation and replaces the previous partial visual overlay with a direct React implementation of the finalized Design Prototype v13 visual contract.

## v13 visual changes now integrated
- Prototype v13 top navigation styling and labels.
- Prototype v13 homepage structure and six feature tiles.
- Prototype v13 player database card conveyor and search-to-card results behavior.
- Prototype v13 collectible player profile front/back card presentation.
- Front card uses the canonical player headshot and player name only.
- Back card uses the dark v13 layout with identity, context controls, SDI snapshot boxes, statistics tables, and top-right six-dimension profile.
- Six-dimension profile opens a configurable overlay with dynamic statistic count and registry-backed statistic selectors.
- Prototype v13 Big Board structure, companion-stat column, and secondary-value grading.
- Existing production API/data contracts remain the source for live player/profile/Big Board data.
- Create Your T75 pairwise ranking engine remains unchanged.
- Explorer, Compare, Teams, Methodology, and the remaining production functionality remain based on Website230.

## Verification
- JSX syntax was parsed/transpiled with the installed TypeScript compiler and produced zero diagnostics for `src/App.jsx` and `src/main.jsx`.
- A full Vite production build was **not** run because the execution environment could not complete the project's npm dependency installation.

## Run locally
1. `npm install`
2. Start the existing local API: `local_api/nba_per75_local_api.py`
3. `npm run dev`
