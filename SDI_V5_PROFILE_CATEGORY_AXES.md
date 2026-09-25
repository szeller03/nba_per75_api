# SDI v5 — Profile Category Axes

Player-profile six-dimension axes now use the same availability-aware evidence
policy as SDI v5.

- Missing statistics are excluded, not assigned 50th percentile.
- Available statistics retain their intended within-group weights.
- Groups with no evidence are excluded; available group weights are renormalized.
- The displayed category performance remains an evidence-based percentile.
- Each axis now also exposes `coverage`, the fraction of the category's intended
  subgroup weight represented by available evidence.
- Coverage is metadata only and does not penalize the category performance.

Example: Oscar Robertson, 1963-64:
- Defense performance: 91.204 percentile (the available DWS evidence)
- Defense coverage: 5%

Thus the system does not claim Oscar was an average defender merely because
steals, blocks, DRtg, relative DRtg, and DBPM were not recorded. It also makes
the limited evidence visible instead of hiding it.

The same helper is used for regular-season and playoff profile spiders, and
5-Year Peak profile axes use the selected peak percentile rows through the same
availability-aware aggregation.
