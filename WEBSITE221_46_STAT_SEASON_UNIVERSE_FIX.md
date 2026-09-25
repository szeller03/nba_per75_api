# Website221 — 46-Statistic Season Universe Fix

The profile UI was incorrectly using the player experience subcategory
aggregation specification as the count of available statistics. That
specification contains 34 rows because it describes dominance subcategory
weights; it is NOT the canonical statistic universe.

The canonical `statistic_registry_v3.csv` contains 46 statistics.

Fixes:
- Regular-season individual player profiles now render the statistic table
  from the canonical 46-stat registry.
- Percentile rows are merged onto those registry rows instead of determining
  which statistics are displayed.
- Therefore a statistic remains visible even if its percentile row is absent.
- Raw values come from the canonical `statistic_values` payload.
- A statistic displays `—` only when its value was not recorded/available in
  the source for that season.
- Replaced the misleading "34 subcategory records" message with a
  season-specific "X of 46 registered statistics recorded" message.
- Career and 5-Year Peak views are not described as individual-season
  recording counts.

Verification:
- Canonical registry: 46 statistics.
- Michael Jordan 1984-85: 46 statistic values, 46 recorded, 46 percentile rows.
- Michael Jordan 1985-86: 46 statistic values, 46 recorded, 46 percentile rows.
- LeBron James 2003-04: 46 statistic values, 46 recorded, 46 percentile rows.
- LeBron James 2024-25: 46 statistic values, 46 recorded, 46 percentile rows.
- Python API syntax check passed.
