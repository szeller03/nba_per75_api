# Website240 Performance Fix 34

Fix 34 targets the remaining Player Profile hot path after Fix 32.

## Changes
- Replaced the season-bundles N+1 percentile query pattern with one seasons query plus one batched percentile query per player.
- Builds season bundles directly from already-fetched payloads, avoiding repeated player-row lookups.
- Keeps Fix 32 thread-local immutable SQLite connections and qualification data unchanged.
- Removes the redundant Regular Season Career profile request; Career comes from season-bundles. Playoff Career still uses the legacy Career aggregate path.
- Extends the frontend API response cache and public player-search cache behavior to 10 minutes to prevent repeated curated-player resolution during normal navigation.
- No SDI formula, qualification rule, peak methodology, statistic definition, ranking rule, or headshot policy was changed.

## Validation
The optimized public_data_layer.py compiles successfully. Direct in-process season-bundles timings against the packaged public database were approximately:
- P002712: 0.56s on first load (includes initial Career-support cache warm), then subsequent calls are substantially faster.
- P002997: 0.014s
- P000387: 0.004s

## Test
1. Start `local_api\nba_per75_local_api.py`.
2. Run `npm run build` and `npm run preview`.
3. Open several Player Profiles in sequence.
4. API log should show season-bundles responses completing without the previous 10–20 second pauses.
5. Verify Regular Season Career and season tables still populate, and spider requests remain separate.
