# NBA PER-75 Website233 — v13 visual completion pass

This package keeps Website230's functional/API/data foundation while replacing the remaining Website230 presentation layers with the v13 prototype visual structure.

## Completed
- Player Database route now uses the v13 basketball-card/conveyor presentation.
- Player Profile now opens as the v13 collectible card and performs lift → quick flip into the dark backside.
- Player Profile no longer exposes individual seasons in a dropdown. Career / 5-Year Peak / Regular Season / Playoffs are the only profile controls; individual seasons are rendered as rows in the season-by-season tables.
- Player Profile season rows load from the existing canonical profile endpoint, including playoff statistics from the playoff statistic payload.
- Player Profile Six-Dimension Profile is populated from the existing SDI category axes and displays the six SDI values. Clicking it opens the configurable statistic radar layer.
- Big Board companion/context values now use a larger companion result set so primary rows are not lost simply because the companion metric ranks differently. Primary and secondary values are displayed to one decimal place.
- Compare now uses the v13 head-to-head visual composition while retaining the existing comparison API, weighted ranges, percentile logic, and six-dimension calculations.
- Explorer now uses the v13 chart-controls / scatter / distribution composition while retaining the existing explorer data source and filtering logic.
- Teams now uses the v13 three-panel overview composition while retaining the existing team analytics/profile API.
- Create Your T75 now uses the v13 choice cards, vertical sealed-pack opening animation, head-to-head matchup presentation, and generated-list presentation while preserving the existing adaptive pairwise ranking engine and T75 candidate pool.

## Verification
- JSX/TypeScript syntax was checked with `tsc --noEmit` using an isolated empty type-root: no syntax diagnostics were returned.
- A full Vite production build was not run because dependency installation in the execution environment timed out. No claim of a completed Vite build is made.
