NBA PER-75 — Player Profile SDI Percentile Correction

BASELINE
- Restored from the last known-good Player Profile SRC baseline.
- Existing local API baseline retained.

ONLY CHANGE
- Individual regular-season Player Profile category SDI values now display the percentile of the raw category SDI within that same season.
- Highest raw category SDI in a season = 100th percentile.
- Lowest raw category SDI in a season = 0th percentile.
- Ties use average rank.
- A one-player qualifying population displays 100th percentile.

NOT CHANGED
- SDI formulas and weights.
- Raw category SDI calculations.
- Overall SDI.
- 5-Year Peak selection/calculation.
- Playoff data or calculations.
- Big Board, Teams, Explorer, Compare, or Create Your T75.
- Player Profile UI architecture.
- Existing performance/cache behavior except the percentile value produced by the existing season spider cache.

SCOPE: SRC + Local API — Player Profiles only.
