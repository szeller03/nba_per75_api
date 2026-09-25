# NBA PER-75 Website89 — Comparison Render Stability Fix

Observed behavior: the comparison request remained on the loading state and then
the browser view became blank after the API eventually returned.

Changes:
- Added a dedicated ComparisonErrorBoundary so a visual/render exception cannot
  blank the entire website.
- Preserved an existing comparison result while a subsequent comparison loads.
- Added a 90-second request timeout with an explicit error state.
- Validated the comparison API response before committing it to state.
- Made statistic and percentile access defensive against malformed/missing
  objects.
- Added containment/min-width CSS around the visual comparison surface.

The underlying comparison API, independent Player A/B ranges, and existing
player-profile functionality are unchanged.
