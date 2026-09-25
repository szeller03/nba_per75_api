# V59 — 5-Year Peak Debug Fix

## Root cause addressed
V57/V58 relied on qualification-population player/season keys that can use legacy/source IDs. When those IDs do not match the canonical master, the peak engine can see zero qualifying seasons and return no rows.

V59 validates the qualification keys against the master and, when the key layer is stale/misaligned, derives the established regular-season qualification directly from the master:
- at least 60% of that season's schedule
- at least 1,400 minutes
Schedule is inferred from the maximum player games in each season rather than hard-coded to 82.

## Regular 5-Year Peak
- Five qualifying seasons
- Maximum six-calendar-season span
- One skipped season allowed
- Two consecutive skipped seasons prohibited
- Big Board is statistic-specific
- Profile is one canonical SDI-selected window
- Profile now explicitly uses REGULAR_STATS

## Playoff 5-Year Peak
- Five consecutive playoff appearances
- Every appearance: >=3 G and >=75 MP
- Five-appearance total: >=35 games
- Big Board and Player Profile support the playoff peak

## Validation
A synthetic smoke test confirmed:
- four qualifying seasons + one skipped season + next qualifying season correctly produces a valid five-season peak
- the peak spans six calendar seasons
- the skipped season is correctly identified
- five playoff appearances at 7 games each correctly satisfy the 35-game threshold
