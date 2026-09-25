# Website232 User Feedback Patch V6

- Player Profile seasonal table percentiles explicitly use Season percentile context.
- Games Played is displayed as a whole number.
- Big Board secondary sorting keeps visible ranks 1, 2, 3... after resorting.
- Player Comparison now loads each selected player's available seasons into start/end dropdowns; blank range means Career.
- Player Comparison percent statistics no longer multiply already-percentage values by 100.
- Player Comparison radar legend uses actual player names and player headshots are larger.
- Team analytics preserve canonical Relative ORtg/DRtg/Pace values from the team master instead of recomputing them from an unweighted mean.
- Team detailed table selected-stat values are bolded rather than given a different font.
- Team profiles display Season, Era, and Historical percentiles for each seasonal statistic.
- Team logo rendering uses the canonical Logo_ID from the team master as the historical asset key, with local/current fallbacks.
- Team seed display uses authoritative competitive-context seed when available, then the existing team-master rank fallback where no seed field is present.
- Create Your T75 final result is column-major, filling ranks 1–10 down the first column before continuing to the next column.
