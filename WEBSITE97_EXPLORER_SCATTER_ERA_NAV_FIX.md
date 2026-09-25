# NBA PER-75 Website97 — Explorer Scatter / Era / Player Navigation Fix

Changes:
- Added a customizable two-statistic scatter plot to Explorer.
- X and Y statistic selectors use the site's statistic registry.
- Scatter data respects Season Type, Era, Season, Scope, Percentile Context, and player search filters.
- Paired observations are matched by canonical player identity plus season/scope label.
- Scatter points are clickable and open the corresponding player profile.
- Explorer leaderboard rows are now clickable and navigate to player profiles.
- Added a working Era selector to Explorer with the same canonical era keys used by Big Board.
- Era selection automatically switches single-season percentile context to Era and resets the season to the all-season view.
- Added Era Average scope using the backend's existing `era`/`era_average` contract.
- Career disables the Era filter because career is intentionally not era-scoped.
- Existing Explorer distribution, leaderboard, percentile, and API behavior preserved.

The scatter implementation is a native SVG visual layer so it does not add a new dependency.
