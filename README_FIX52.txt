FIX 52 — Big Board Data + Logic

Built from NBA_Per75_Black_RoseGold_White_Red_VHS_NoRectangles_v22.

Changes:
- Explicit Big Board secondary-stat mapping; no global fallback.
- Secondary columns are hidden entirely for statistics without a documented companion.
- Secondary values now work across Single Season, 5-Year Peak, Era Average, Career, and Playoffs by matching the primary scope.
- Percentage values render as true percentages (e.g. 58.5%, not 0.6%). AST:TOV renders to two decimals.
- ORtg and DRtg removed from the Big Board statistic selector.
- PF/75 uses descending raw-value ordering when Highest first is selected.
- Added request caches for Era Average and 5-Year Peak Big Board requests.
- No statistical source data or locked formulas were changed.

Modified:
- src/App.jsx
- local_api/nba_per75_local_api_phase4_v3.py
- local_api/public_data_layer.py

API restart required: YES (local_api changed).

FIX 52 v30: restored career BRef qualification constants; SDI bypasses public single-season shortcut; vectorized Era Average aggregation; reuses canonical precomputed regular 5-Year Peak profile bundle when available.

FIX 52 v32:
- Restored the Career Big Board dispatch that was accidentally dropped in v31, including AST:TOV and the audited WOWY career route.
- Career Per-75 rates such as AST/75 are reconstructed from career totals and estimated possessions when the canonical career export omits the rate column.
- Era Average secondary values now resolve canonical statistic aliases and reconstruct AST:TOV from raw AST/TOV or Per-75 totals when needed. Era rows also expose companion_values as a fallback to the UI.
- 5-Year Peak Big Board no longer reuses the Player Profile's SDI-selected canonical peak window. It remains statistic-specific and evaluates each valid five-season window using the underlying data.
- 5-Year Peak Per-75 aggregation is possession-weighted; if explicit possessions are unavailable it derives possessions from PTS and PTS/75 before using the MP*2 fallback. It never simply averages the five displayed season rates.
- Missing historical Per-75 peak statistics are reconstructed from underlying raw totals when available, including BLK/75.
- Added a persistent weighted regular 5-Year Peak Big Board cache so once the authoritative statistic-specific bundle is built, subsequent selector changes and API restarts can use a file/in-memory lookup.
- Player Profile functionality/data/calculations remain untouched.


Compare functionality pass: canonical WOWY values merged into comparison source; Engine & Playmaking taxonomy/order updated; DREB% added to Rebounding; defense/impact WOWY rows wired; tie rows use a full-width white gradient. Big Board and Player Profiles remain locked.
