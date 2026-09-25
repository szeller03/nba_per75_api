# Website73 — Playoff 5-Year Peak Repair V1

This version keeps the Website71/72 React + Vite frontend and repairs the
canonical playoff 5-Year Peak source used by the included local API.

## Locked rules
- Exactly five consecutive playoff appearances.
- Every appearance must meet >=3 games AND >=75 minutes.
- The five appearances must total >=35 games.
- Player Profile selects the window by the highest average season-level
  playoff Statistical Dominance Index (SDI).
- All 46 displayed peak statistics use the same selected five-appearance
  window.
- Peak-context percentiles are calculated across the canonical playoff
  5-Year Peak population, not substituted from regular-season data.
- The playoff peak spider consumes those same Peak_Percentile values.

## New diagnostics
`GET /api/v1/playoff-peak-diagnostics`

## Important
The frontend remains React/Vite. The included local API remains the canonical
backend for this Website73 package and reads the established NBA_Per75 data
root. No scraping or SDI recalculation of the regular-season v5 source is
performed.
