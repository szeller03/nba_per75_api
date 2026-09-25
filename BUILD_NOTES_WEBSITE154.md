# Website154

Changes:
- Added the complete early BAA/NBA season-specific BRef thresholds supplied by the user for FG%, FT%, and TS%.
- Added the full NBA season-by-season 3P% threshold progression.
- Added the supplied ABA season-specific 3P/FG/FT/TS thresholds.
- Added BRef career percentage minimums:
  NBA: FG 2,000; FT 1,200; 3P 250; TSA 5,000.
  ABA: FG 1,000; FT 600; 3P 125; TSA 2,500.
- Added a 15,000 career-minute floor for career Per-75 boards only.
- Kept the known-good Big Board canonical ranking/value pipeline intact: BRef rules
  are qualification gates and do not replace PTS/75 or other requested values.
- Added caching of the BRef eligibility gate by statistic/season type so repeated
  Big Board requests do not rebuild the full qualification population.
