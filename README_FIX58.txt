FIX58 — Profile SDI Display Baseline

Built directly from FIX51, the last confirmed working SDI companion-percentile baseline.

Changes ONLY the Profile presentation plumbing:
- Profile displays percentile only.
- Existing raw SDI remains in the backend/data and Big Board paths.
- Playoff and playoff-peak category axes expose their already-computed percentile composite as the Profile percentile so they render instead of disappearing.
- No SDI formulas, source datasets, headshots, weights, or canonical caches were rebuilt or replaced.

This is intentionally a minimal rollback-to-known-good architecture, not another canonical SDI rebuild.
