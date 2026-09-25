# NBA PER-75 Website88 — Comparison Visual Layer

Built on the working independent-range comparison.

Added:
- Six-dimension dominance spider chart.
- Six-dimension category bars.
- Statistic percentile visual cards.
- Full raw-stat head-to-head table with percentile columns.
- Player A/B range summaries.
- Graceful fallback to relative raw-stat visualization when comparison
  percentiles are not returned.
- No changes to canonical player-profile calculations.

Canonical six dimensions:
Scoring Volume, Scoring Efficiency, Creation & Playmaking, Rebounding,
Defense, Impact & Value.

Percentile rendering is driven by the comparison API when percentile values
are present. The visual layer explicitly labels the fallback state if the
API still returns null percentile values.
