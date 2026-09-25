# Playoff SDI — Small-Sample Percentage Rule

Locked rule: percentage statistics are denominator-aware.

- 3P% is eligible only when 3PA > 0.
- 2P% is eligible only when 2PA > 0.
- FT% is eligible only when FTA > 0.
- TS%, FTr, and 3PAr are eligible only when FGA > 0.
- Zero attempts produce a missing statistic/percentile, not a 0% shooting result.
- The existing SDI aggregation layer renormalizes the remaining available statistic weights within the affected group.
- A player who actually attempts shots and shoots poorly is still evaluated normally; only zero-denominator cases are excluded.

Regular-season SDI code and frontend/design files are not changed by this rule.
