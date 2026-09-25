# NBA PER-75 Website91 — Comparison Percentile Source Fix

The comparison values and visuals were working, but percentile cells remained
blank because the comparison API was searching only the newer historical
percentile directory. The finalized project already contains
`player_profiles_v1/player_percentile_lookup_v1.csv`, which is the canonical
player-season percentile lookup used by the website.

Website91:
- Prefer `player_percentile_lookup_v1.csv` for regular-season comparison
  percentiles.
- Fall back to finalized season percentile Big Board sources.
- Use playoff percentile sources for playoff comparisons.
- Match player identity by ID first, then clean public name.
- Match season labels/end years robustly.
- Support common statistic-name aliases such as `FG%` vs `FG_pct`.
- Support both `Percentile_Stat` and `Stat_Percentile` column layouts.
- Preserve Season / Era / Historical context.
- Preserve independent Player A and Player B ranges.
- Add comparison diagnostics showing the actual percentile source selected.

No statistic values or weighting formulas were changed.
