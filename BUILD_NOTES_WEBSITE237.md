# NBA PER-75 Website237

## Follow-up fixes

### Player Profiles
- Fixed relative defensive rating coloring so negative rDRtg / Relative_DRtg values use the light-blue good color and positive values use the light-red bad color.

### Big Board
- Restored companion-stat detection using normalized statistic keys, so display-label variations such as FGA/75, 3P%, etc. still resolve to the canonical companion mappings.
- Secondary columns remain suppressed only for the explicitly requested no-secondary statistics.

### Comparison
- Restored the six-dimension spider chart below the percentile dimension bars and enlarged it substantially.
- Added transparent red/gold half-row tinting to the side of each comparison stat row belonging to the statistical leader.
- Added AST:TOV and rORtg to Creation & Playmaking.
- Added rDRtg to Defense.
- Added NRtg to Impact & Value.
- rDRtg is treated as lower-is-better in comparison leader logic.

### Teams
- Added ESPN current-team logo fallback after historical logo lookup and before the remaining canonical/current fallbacks. This is intended to eliminate the recurring missing-logo cases for Celtics, Suns, and Thunder seasons.
