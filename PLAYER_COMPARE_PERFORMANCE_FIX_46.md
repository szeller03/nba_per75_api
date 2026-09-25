# Website240 Performance Fix 46 — Player Compare

Built from the validated Fix 45 Big Board baseline.

## Scope
- Optimize only the Player Compare request path.
- Preserve the Player Profile Performance Lock.
- Preserve the working Big Board public/cache delivery path.
- Preserve comparison calculations, season weighting, percentile contexts, WOWY statistics, headshots, and UI.

## Backend optimization
`/api/v1/compare` previously resolved percentile data separately for each statistic, repeatedly scanning the canonical percentile DataFrame. Fix 46 resolves all requested statistics for each player with one source narrowing pass, then reindexes the small player/year frame.

## Frontend optimization
Selecting a player previously caused a season-list request in `choose()` and then another identical request from the `playerA`/`playerB` effects. Fix 46 makes the effects the single owner of those requests, removing the duplicate request without changing the UI behavior.

## Safety
No Profile request orchestration, Profile caches, Big Board endpoints, SDI methodology, WOWY data source, qualification rules, peak methodology, or headshot logic were changed.
