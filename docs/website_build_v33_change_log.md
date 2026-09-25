# V33 — Playoff Percentile Layer

Uses the established project playoff qualification definitions:
- single-season/all-time playoff qualifier: 7 games + 125 minutes
- career playoff qualifier: 50 games + 1,500 minutes

Season output retains every canonical playoff player-season and its statistical
values. Percentiles are null for non-qualified seasons.

Career output retains every playoff career and its statistical values.
Career percentiles are null for non-qualified careers.

Three season contexts are generated:
- Season
- Era
- Historical

Career has its own percentile context and is not a Season/Percentile Context
filter.

Percentile ranking uses the established average-rank 0-100 method.

No identity or source data are overwritten.
