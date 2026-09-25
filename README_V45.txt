NBA PER-75 Big Board v45

Scoped fixes from v44:
- Secondary percentile row gradient now flows right-to-left.
- Every Big Board row is explicitly styled/clickable as a player-profile navigation target.
- Career WOWY weighting now has robust fallback to the canonical master or player-season profile layer instead of returning an empty board when the finalized master path/layout is unavailable.
- Career WOWY still uses the existing 400-game / 10,000-minute eligibility contract and minutes-weighted aggregation.
- No Player Profile functionality/data/calculation changes.
- No Peak/Era/Single Season load-time architecture changes.
