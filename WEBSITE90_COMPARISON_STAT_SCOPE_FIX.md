# NBA PER-75 Website90 — Comparison `stat` Scope Fix

Website89 successfully isolated the Compare render failure and exposed the
exact error:

    Render error: stat is not defined

Website90 removes the ambiguous statistic-variable references in the
comparison visual calculations and uses explicit `metric` callback variables.
The percentile/statistic visual maps remain scoped to their own `map(metric)`
callbacks.

No comparison API calculations, independent season ranges, player profiles,
or source data were changed.
