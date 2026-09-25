# Website234 — September 8, 2026 user feedback patch

## Player Profiles
- Fixed WS/48 to resolve to the canonical decimal WS/48 field (`WS/48.1`) instead of the rounded WS/48 display field.
- rORtg/rDRtg values are light blue when positive and light red when negative; percentile badges remain white/independently graded.
- Added `+` prefix for positive NRtg, rORtg, and rDRtg values.
- FTr and 3PAr display to two decimal places.

## Big Board
- Removed the secondary/context column entirely when no companion statistic is requested.
- Updated companion statistics per the September 8 specification, including shooting percentages, rates, ratios, relative ratings, and On-Court ratings.

## Compare
- Enlarged and centered the red VS marker.
- Moved the six-dimension spider chart above the six dimension percentile bars.
- Reorganized category statistics:
  - PTS/75 moved to Scoring Efficiency.
  - FTr and 3PAr moved to Scoring Volume and use two decimals.
  - Added rORtg to Creation & Playmaking; removed BPM.
  - Added rDRtg to Defense; removed DREB%.
  - Added On-Court ORtg / On-Court DRtg labels to Impact & Value.
  - Impact & Value uses WS/48 rather than overall WS.
- On-Court ORtg / DRtg labels are used where requested.

## Explorer
- Current implementation forms the scatter pool by fetching up to 1,000 rows independently for X and Y using the same view/scope/season/season-type/context filters, then intersecting them by player + season. The chart renders the first 100 matched rows from the X-side ordering. This means X=PTS/75, Y=rTS is not a universal player pool; it is the intersection of the two statistic result sets under the current filters, ordered by the X statistic.

## Teams
- Modern-season team logo fallback now prefers the NBA CDN logo before historical-logo fallbacks, addressing missing Suns/Thunder/Celtics-style current logos while preserving historical logos for older seasons.
- Populated regular-season Opponent TOV% and Opponent eFG% from the existing cached Basketball-Reference team opponent tables in the supplied NBA_Per75 project, using opponent TOV / possession denominator and opponent eFG formulas. Historical seasons without the necessary 3P fields remain unavailable for Opponent eFG% rather than being fabricated.
- Updated the bundled team analytics cache with the populated regular-season opponent factors.
