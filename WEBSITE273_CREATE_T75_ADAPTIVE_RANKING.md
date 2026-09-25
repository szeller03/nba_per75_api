# WEBSITE273 — Create Your Top 75 Adaptive Ranking + Tighter Pool Cards

## UI
- Tightened direct-selection player cards again to reduce empty vertical space.
- Increased portrait dominance and tightened the nameplate.
- Preserved gold tint, selection states, search, ordering, and responsive behavior.

## Head-to-head engine
Replaced the fixed-budget Elo-style ranking flow with an adaptive pairwise ordering engine.

### Core behavior
- Every answer is recorded as a directed relation: winner > loser.
- Transitivity is used for free through a directed acyclic graph / topological ordering.
- The engine checks whether the first X positions are uniquely determined.
- If the requested Top X is uniquely resolved, the session ends immediately — no arbitrary remaining question budget.
- When unresolved, the next matchup is selected from candidates capable of occupying the next unresolved position, favoring close canonical-pool neighbors and then pairs near the Top-X boundary.
- The final ranking uses the proven topological order whenever the requested Top X is uniquely resolved.

### Accuracy note
This can produce an exact ordering from fewer questions than a fixed all-pairs approach when the user's answers create enough transitive structure. It does not claim that every arbitrary total ordering can be identified in fewer than the information-theoretic number of comparisons, and inconsistent/cyclical answers cannot define a mathematically exact ranking.

## UI copy
- Removed the misleading fixed "X decisions max" messaging.
- Head-to-head flow now says that the engine uses adaptive comparisons and stops once the requested ranking is fully resolved.
- The progress display now shows comparison count and "ADAPTIVE · NO FIXED QUESTION COUNT" instead of pretending there is a fixed quota.
