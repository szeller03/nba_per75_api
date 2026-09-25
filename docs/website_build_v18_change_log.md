# V18 — Full Profile Season Universe + Career Leaderboard Framework

## Player profiles
- The master 36,251 player-season universe is now authoritative for profile season navigation.
- A player-season is never removed merely because it lacks percentile qualification.
- Qualified seasons continue to receive enriched percentile/profile fields.
- Unqualified seasons remain visible with their raw master statistics; percentile fields may be unavailable.
- Career raw profile data remains available independently of percentile qualification.

## Career percentiles
- Career percentiles are calculated from career-aggregated raw values, never by averaging season percentiles.
- A career percentile is only assigned after the existing qualification-population gate.
- Raw career values remain available even when the career percentile is not qualified.
- The qualification gate is intentionally configurable; a statistic-specific career minimum threshold has not been invented.

## Big Board
- Added Career as a Big Board scope.
- Career is integrated into the same Big Board rather than creating a separate tool.
- All registered statistics can be selected under Career.
- Career percentile ranking is based on career values.
- Current career aggregation is explicitly provisional/configurable: cumulative-like statistics sum; rate/rate-like statistics average.
- Statistical Dominance Index career aggregation is not yet finalized and is not presented as a finished methodology.

No source/master analytical data was modified.
