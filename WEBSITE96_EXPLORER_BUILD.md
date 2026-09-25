# NBA PER-75 Website96 — Statistical Explorer

Built the next major website feature: the Statistical Explorer.

The previous Explorer was a placeholder. Website96 now provides:
- Statistic selector using the site's statistic registry.
- Regular Season / Playoffs selector.
- Season selector, including all available seasons.
- Season / Era / Historical percentile context.
- Player-season scope with the existing API contract preserved.
- Optional player search/filter.
- Population summary cards.
- Value distribution histogram.
- Sortable-by-API highest-performing leaderboard.
- Adjustable 25 / 50 / 100 row display.
- Click any leaderboard row to highlight an observation.
- Direct link to the selected player's profile.
- Existing API and player-profile/comparison systems are preserved.

The Explorer intentionally uses the existing Big Board percentile source rather
than introducing a second statistical data pipeline. The visual design is
functional only and can be redesigned later.
