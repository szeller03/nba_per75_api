# Player Profile Performance + Season State Phase 6

Built from the user's previously fast profile source as the performance baseline. This is NOT a rollback of the later functionality; the API/profile improvements from Phase 5C are layered onto that baseline.

## Changes
- Keeps Phase 5C request deduplication and profile prefetch in `src/api.js`.
- Keeps later Player Profile additions including WOWY ordering, playoff percentile handling, career qualification presentation, and historical 2P display handling.
- Restores persistent individual-season rows with an independent per-player/per-season-type bundle cache.
- Individual season rows are never cleared merely because a context switch or transient bundle request fails.
- Career NQ is gated behind an explicit qualification-loading state. While qualification is unresolved, the UI does not display NQ.
- Career qualification is resolved from the returned canonical Career payload when available, with the locked fallback thresholds (Regular Season 400 games/10,000 minutes; Playoffs 50 games/1,500 minutes).
- Does not modify backend data, headshot assets, or headshot rendering assets.
- Prefetch is initiated from existing Players/Big Board hover/pointerdown behavior, while the active profile request remains independent.

## Files changed
- `src/App.jsx`
- `src/api.js`

All other files are copied unchanged from the supplied fast-source ZIP.
