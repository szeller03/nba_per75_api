# NBA PER-75 Website93 — Canonical Comparison Percentile Fix

The screenshot confirmed the visual layer is rendering, but nearly all
statistic percentiles were blank. The prior comparison implementation was
reading a wide percentile lookup and trying to infer column names.

That was the wrong abstraction.

The player-profile endpoints already use the canonical long-format
`player_season_percentiles_long` source and the shared `percentile_column()`
selector. Website93 makes the comparison API use that exact same source for
regular-season comparisons.

For each selected player/stat:
1. Match Player ID, then cleaned player name.
2. Match the selected season end year.
3. Match the statistic in the long-format `Statistic` column.
4. Use the canonical Season/Era/Historical percentile selector.
5. Fall back between canonical contexts only when the requested context is
   unavailable.
6. Weight those per-season percentiles by the same selected-season weights
   used for the comparison.

Playoff comparisons retain the existing playoff percentile path.

No visual calculations, player ranges, statistic values, or weighting
definitions were changed.
