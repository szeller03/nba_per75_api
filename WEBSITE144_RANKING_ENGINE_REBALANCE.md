# Website144 — T10/T25/T50/T75 Ranking Engine Rebalance

The previous version could produce unstable-looking outcomes because it used
raw win totals and relatively small decision budgets across very large pools.

## New candidate-field sizes
- T10: 15 candidates, 60 decisions max
- T25: 30 candidates, 110 decisions max
- T50: 60 candidates, 200 decisions max
- T75: 90 candidates, 300 decisions max

These are taken from the cumulative candidate tiers supplied by the user,
preserving the submitted order within each tier.

## Ranking model
The result is no longer sorted by raw win count. It now uses an iterative
pairwise strength rating (Elo/Bradley-Terry style), so beating a strong
opponent contributes more meaningful information than simply accumulating
wins against weak opponents.

## Matchup selection
After every candidate has appeared at least once, matchups prioritize:
- similarly rated players,
- unresolved nearby players,
- players around the requested cutoff,
- and pairs that have not previously been shown.

The duplicate-pair protection remains active.

## Result
The final screen still shows the requested list plus only the five players
immediately outside the cutoff.
