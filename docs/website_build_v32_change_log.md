# V32 — Missing Career Statistic Fix

V31 failed when a career statistic was unavailable for a player but career
estimated possessions existed. The calculation attempted `None / possessions`.

V32 only calculates a career Per-75 value when both the underlying career
statistic and career estimated possessions are available and possessions are
positive.

Missing historical statistics remain missing and are never treated as zero.

No identity decisions or qualification rules changed.
