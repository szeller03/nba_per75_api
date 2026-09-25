# V14 — Big Board Raw Values

Fixed the Big Board so it displays the actual statistic value alongside the percentile.

The visualization Big Board source can contain percentile data without carrying
the raw statistic value. V14 therefore falls back to the canonical
player-season percentile source to retrieve the raw value for the selected
statistic and season.

Default Statistical Dominance Index rows continue to display the actual Index
score. No source/master analytical data was modified.
