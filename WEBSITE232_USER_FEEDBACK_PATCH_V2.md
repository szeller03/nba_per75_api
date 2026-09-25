# Website232 User Feedback Patch V2

Applied: player headshot loading/retry, profile radar vertex alignment and label sizing, burgundy configurable radar, Big Board clickable secondary-stat three-state header sorting, Explorer quantile-based bounds, T75 headshot containment, and Basketball-Reference-derived team playoff success integration.

Percentile note: the project already contains the canonical regular-season long percentile source under `player_analytics_v1_2_dreb/historical_percentiles_v2_1/`. The Magic Johnson example should be checked against that source. If the problematic display is specifically a playoff percentile, the regular-season master is not the appropriate source; the playoff percentile layer is generated separately by the API.
