# Website Build V48 Change Log

## Purpose
Repair career qualification integrity, add era-wide player aggregation, and stabilize intermittent spider-chart updates.

## Changes
- Corrected regular-season career percentile qualification from the incorrect 50 G / 1,500 MP gate to the established **400 G / 10,000 MP** gate.
- Preserved the established playoff career threshold of **50 G / 1,500 MP**.
- Added Big Board `Era Average` scope for Regular Season and Playoffs.
- Added era-average qualification thresholds:
  - Regular Season: 40% participation + 250 G + 6,000 MP.
  - Playoffs: 40% participation + 40 G + 1,250 MP.
- Added era-average percentile populations, calculated within the selected era.
- Added denominator-aware aggregation for per-75, additive, percentage, ratio, and minute-weighted metrics.
- Added era-average metadata to Big Board rows (participation, qualified seasons, eligible seasons, games, minutes).
- Added UI guidance for Era Average methodology.
- Added request-generation protection to Player Profile spider fetches to prevent stale async responses from overwriting current selections.
- Left Statistical Dominance Index implementation untouched/deferred.

## Validation
The API was exercised against the supplied NBA_Per75 data package. Example 2000-01 through 2009-10 Era Average PTS/75 results returned successfully for both Regular Season and Playoffs, and the regular-season career Big Board now reports the 400 G / 10,000 MP qualification note.
