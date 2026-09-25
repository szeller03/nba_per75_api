FIX55 — Canonical Creation SDI correction

This patch is based on FIX54.

Changes:
- Uses the existing canonical regular-season WOWY-RtS SDI season cache as the
  authoritative regular-season SDI cache. This cache is the already-built
  variant with the locked Creation Ball Security rule: AST:TOV = 100%, TOV% = 0%.
- Career Profile Creation is anchored to the corrected canonical season Creation
  scores, MP-weighted across the player's career seasons, and ranked against the
  qualified career population.
- 5-Year Peak Creation continues to use canonical season category scores.
- No headshots changed.
- No raw SDI values are removed from the data layer.
- Profile presentation remains percentile-only.
