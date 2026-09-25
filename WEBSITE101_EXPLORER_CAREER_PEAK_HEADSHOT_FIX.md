# NBA PER-75 Website101 — Explorer Career / 5-Year Peak / Headshot Fix

Fixes:
1. Playoff Career:
   The Explorer had been routed to a nonexistent `_playoff_career_big_board`
   helper. It now calls the existing playoff career implementation directly
   with `scope=career` and `season=Career`.

2. 5-Year Peak:
   Added `5-Year Peak` to Explorer scope. It uses the existing canonical
   five-year peak Big Board implementation and works for Regular Season and
   Playoffs. Era is disabled for this scope because the peak builder already
   has its own population/qualification contract.

3. Scatter headshots:
   Native SVG image rendering was still not reliable in the browser. The
   scatter now renders headshots as regular HTML buttons absolutely positioned
   over the SVG coordinate system. This avoids SVG image/foreignObject/CORS
   rendering issues while preserving responsive positioning.
   - Headshots remain clickable.
   - Hover enlarges them.
   - Missing headshots fall back to the normal scatter circle.
   - Tooltips still show player, season, X and Y values.

The scatter continues to use the same filters and paired-observation
intersection logic.
