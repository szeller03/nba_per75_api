# Website217 — Player Profile Data Integrity Fix

This build addresses the regressions exposed after the SDI v4 peak cache became
visible.

Fixed:
1. Six-dimension spider/category axes were empty because the aggregation CSV
   used internal lowercase category keys while the API expected display names.
   The spec now uses the six display names while retaining the locked weights.
2. Regular-season spider/context requests now normalize `YYYY-YY` season labels
   to the canonical season-end-year stored in the percentile source.
3. `find_csv()` could select an unrelated CSV when the requested canonical file
   was absent; it now requires a real filename-term match.
4. The regular career builder previously returned player-season rows as career
   rows. A canonical `data/nba_per75_career_v2.csv` is now included.
   Career G/MP are summed; per-75/rate/index statistics are minutes-weighted;
   additive value statistics WS/OWS/DWS/VORP are summed.
5. Headshots: the canonical registry remains preferred. When it is not bundled,
   the API now has a cached Wikimedia thumbnail fallback so profile/search
   pages can still resolve a player image instead of returning null.

Verified in-process:
- Jokic regular 5-Year Peak remains 2021-22 through 2025-26.
- Jokic career = 810 G, 25,914 MP, 25.605 PTS/75, 12.769 TRB/75,
  8.642 AST/75, .6404 TS%, 142.7 WS.
- Season, Career, and Peak spiders each return all six SDI dimensions.
