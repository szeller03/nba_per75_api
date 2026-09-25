# Playoff SDI — Locked Formula Contract

The regular-season SDI formula is read-only. Playoff SDI is its exact formula projected into the postseason with only these changes:

1. Remove Defense entirely.
2. Remove Impact & Value entirely.
3. In Creation & Playmaking, remove WOWY Offensive Impact (30% of the regular Creation category) and proportionally renormalize the remaining groups:
   - Creation Output: 38.5% -> 55%
   - Ball Security / Creation Cost: 31.5% -> 45%
4. Scoring Volume, Scoring Efficiency, and Rebounding retain the regular-season subcategory/statistic weights exactly.
5. Scoring Efficiency is:
   - Overall Efficiency 60%: TS% 25%, rTS 75%
   - Component Efficiency 40%: 2P% 50%, 3P% 40%, FT% 10%
   - FG% is not included.
6. The four retained top-level categories keep their regular-season relative weights (20%, 18%, 18%, 10.5%) and are renormalized to 100% after Defense and Impact & Value are removed.
7. The Player Profile's visible playoff SDI category values are the percentile ranks of the NEW category SDI scores against the appropriate playoff population. They are not generic percentiles of individual statistics.
8. The overall playoff SDI is also computed from the four new category scores and an overall percentile is exposed as `sdi_percentile`.

No `src/` frontend files are changed by the playoff SDI work.
