# Website240 Performance Fix 32

Targets the latest API-log bottlenecks without changing basketball methodology.

### Fixes
- Per-thread read-only SQLite connections eliminate concurrent `/public/players` cursor collisions (`InterfaceError` / `IndexError`).
- SQLite immutable/read-only + memory temp settings improve hot-path queries.
- Frontend API adds a 30-second response cache and coalesces simultaneous identical GET requests.
- Regular-season Career and selected-season profile views use the indexed public `season-bundles` layer rather than the slow legacy pandas profile route.
- Removes the duplicate regular-season Career profile request. Playoff Career remains canonical/legacy.
- Retains Fix30 qualification and Career sidecars plus production Vite bundle configuration.

### No methodology changes
SDI weights, qualification thresholds, peak rules, statistics, percentile definitions, and ranking logic are unchanged.

### Build
Start API with `python local_api\nba_per75_local_api.py`, then run `npm install` and `npm run build`. Use `npm run preview` to test production mode.
