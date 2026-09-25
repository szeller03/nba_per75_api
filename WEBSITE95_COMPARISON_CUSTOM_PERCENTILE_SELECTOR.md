# NBA PER-75 Website95 — Custom Statistic Percentile Selector

The Comparison percentile profile is now customizable instead of being fixed
to the first 12 statistics.

Behavior:
- All statistics returned by the comparison API (currently 46) are available.
- The default view remains the first 12 statistics so the page does not become
  unnecessarily long.
- `Choose statistics` opens a searchable checkbox picker.
- Users can select any combination of the 46 statistics.
- `All`, `Reset`, and `Clear` controls are provided.
- The selected count is shown in the picker.
- The underlying raw-stat comparison table still contains all returned
  statistics.
- Percentile values continue to come from the canonical percentile pipeline
  fixed in Website93.
- No data, weighting, percentile calculation, or overall site design was
  changed.

This is intentionally a functional control rather than a final visual
redesign, so the picker can be restyled later with the rest of the site.
