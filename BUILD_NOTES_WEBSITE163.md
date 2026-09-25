# Website163 — NEW SDI v4 Player Profile Peak + duplicate identity repair

## What changed

### Michael Jordan / duplicate player search results
- Added a final deduplication pass directly in `api_players`.
- Same normalized name + materially overlapping authoritative master-season
  histories are treated as one public player.
- The ID with the largest authoritative season footprint is retained.
- Genuine same-name players with non-overlapping careers remain separate.
- `_canonical_player_id_for_name` now resolves duplicate-name IDs using the
  authoritative master season footprint rather than simply taking the first
  identity row.

### 5-Year Peak — NEW SDI v4 formula
- The regular Player Profile 5-Year Peak no longer uses
  `player_statistical_dominance_v1`.
- It now uses `config/statistical_index_v4_locked.json`, the locked NEW SDI v4
  formula:
  1. weighted statistic percentiles -> subgroup scores
  2. weighted subgroup scores -> category scores
  3. equal weighting across the six top-level categories
- Season-level SDI values are built from the canonical Season Percentile
  population.
- A compact `local_api/cache/regular_sdi_v4_player_seasons.csv` is persisted
  after the first build.
- The API warms this compact index at startup, so clicking 5-Year Peak does
  not trigger the expensive league-wide calculation.
- Each player's completed 5-Year Peak response remains cached in memory.
- The old request-time all-player peak reconstruction is disabled.
- The old dominance-index source is therefore no longer a fallback for the
  regular Player Profile peak.

### Peak window rules retained
- Five qualifying regular seasons
- Maximum six-calendar-season span
- One skipped/non-qualifying season allowed
- Two consecutive skipped seasons prohibited
- Highest average NEW SDI v4 across the five included seasons selects the
  canonical window
- All displayed peak statistics continue to use that same selected window
