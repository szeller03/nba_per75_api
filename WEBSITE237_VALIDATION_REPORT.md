# Website237 Validation Report

## Completed
- WOWY Offense, WOWY Defense, and WOWY Net are first-class regular-season player statistics.
- Individual player rORtg/rDRtg/NRtg/Relative_NRtg are removed from the player statistic registry and regular player statistic contract.
- Team rORtg/rDRtg/NRtg remain in the Teams layer.
- WOWY raw values and audited season percentiles are merged into the canonical player-season statistic layer.
- Player Profile now injects WOWY values and season percentiles into the live response.
- Big Board can rank WOWY Offense/Defense/Net using their audited seasonal percentiles.
- Career WOWY boards are available using available-season aggregation.
- Regular-season SDI single-season, career, and peak board paths now consume the WOWY-aware SDI cache rather than the stale pre-WOWY season cache.
- Frontend headshots render only through the local canonical headshot API endpoint; raw B-Ref image URLs are no longer rendering candidates in React.
- Headshot API resolution prefers NBA CDN assets from the finalized registry, including Original_NBA_CDN_URL when the finalized row is a fallback row.

## Smoke tests
- `/api/v1/statistics`: PASS — WOWY Offense/Defense/Net present; individual NRtg/Relative_ORtg/Relative_DRtg/Relative_NRtg absent.
- Jordan 1987-88 Profile: PASS — WOWY Offense 4.9, WOWY Defense 2.8, WOWY Net 7.7; season percentiles 98.71, 98.71, 100.00 respectively.
- Jordan 1987-88 WOWY Net Big Board: PASS — Jordan ranks first at 7.7 / 100th seasonal percentile.
- SDI spot-checks: WOWY-aware SDI differs from stale pre-WOWY SDI for tested recent seasons (e.g. Jordan 2002-03: 71.5969 vs 66.6633; LeBron 2025-26: 73.4417 vs 69.3275; Jokić 2025-26: 89.6552 vs 88.2111).
- Python API syntax: PASS.

## Environment limitation
The Vite production build could not be executed in the container because the platform's installed Rollup optional native dependency was unavailable and package installation timed out. The source/API validation above passed. The archive intentionally excludes node_modules so the user's normal `npm install`/existing project environment can build it.

## Important scope note
Regular-season WOWY statistic integration is complete. The dynamic regular 5-Year Peak statistic board can consume WOWY as a first-class stat. The SDI 5-Year Peak board is wired to the WOWY-aware season SDI source, but a future fully canonical peak-SDI rebuild should recalculate the composite from the aggregated five-year underlying statistic data rather than simply aggregating season SDI scores.
