# Website155

- Fixed career percentage qualification: raw career totals are now retained
  from the canonical career file for BRef attempt thresholds.
- Career FG%, FT%, 3P%, and TS% boards now exclude sub-threshold careers
  instead of merely removing their percentile while leaving them in the ranked
  output.
- AST_TOV is exposed in the Big Board statistic registry as `AST:TOV`.
- AST_TOV remains the canonical statistic/value; no recomputation is done for
  single-season rows.
- AST:TOV is treated as higher-is-better.
