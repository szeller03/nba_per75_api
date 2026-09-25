# NBA PER-75 Website94 — Comparison Functional Completion

Added the next non-visual comparison features while leaving the overall design
intentionally unchanged:

- Independent selected-season audit for both players, using the exact seasons
  returned by the API.
- Expandable methodology section showing the comparison weighting rules.
- Category-level A/B lead indicator.
- Raw-stat leader column that respects lower-is-better statistics for known
  defensive/turnover/foul metrics.
- Percentile delta column.
- Percentile leader column, where higher percentile always wins.
- Existing difference column retained.
- Existing independent Player A/B ranges retained.

AST:TOV note:
The current canonical statistic registry/percentile data contains no AST:TOV
statistic or AST:TOV percentile. This is therefore not a missing frontend
display field; it would require defining AST:TOV as a derived statistic and
adding it to the canonical statistic/percentile pipeline. It was not silently
added in Website94 because that changes the site's statistical contract.
