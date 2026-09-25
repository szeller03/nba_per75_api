# V9 — Career Percentile Layer

Career percentile data is now available in the player profile.

Method:
- Career percentile is NOT the average of season percentile ranks.
- For each statistic, the player's numeric season values are averaged across available seasons.
- That career-average statistic is ranked against the full player career population for the same statistic.
- The resulting percentile is exposed as `Career_Percentile`.
- Season/Era/Historical percentile calculations remain unchanged.
- Career remains a separate percentile context and does not fabricate an average percentile rank.

The 46-stat career percentile table now displays Career Value and Career Percentile.
