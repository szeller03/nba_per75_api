# Route A — SDI Companion Percentile Integration (Backend/Data Layer)

This package locks in Route A:
- The existing weighted SDI composite remains the PRIMARY SDI score.
- A percentile of that completed composite is added as a COMPANION metric.
- No SDI score is re-percentiled or replaced.
- No Player Profile visual placement is changed in this phase.

The installer works against an existing NBA_Per75_Website241 (or similarly structured) folder.

It:
1. Backs up each SDI CSV before changing it.
2. Finds the Career SDI CSV and adds companion percentile columns.
3. Looks for regular-season 5-year peak, playoff career, and playoff 5-year SDI CSVs using filename patterns and adds companion percentiles when the relevant composite columns exist.
4. Uses the qualified population in each file when a qualification column is available.
5. Uses the standard tied-rank percentile formula:
      100 * (N - average_rank) / (N - 1)
   where higher composite score = better.
6. Leaves all existing SDI values untouched.

Important:
- This package does NOT change the frontend layout.
- It does NOT convert Route A scores into percentiles.
- It only creates the companion percentile data so the next Player Profile redesign can choose where to display it.

Run:
  python apply_route_a_companion_percentiles.py "C:\path\to\NBA_Per75_Website241"

A report is written to:
  route_a_companion_percentile_report.json
