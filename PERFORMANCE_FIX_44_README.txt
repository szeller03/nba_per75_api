Website240 Performance Fix 44 — Big Board materialized cache

Purpose
- Preserve the locked Fix 42/36 Player Profile architecture.
- Materialize the existing regular-season Big Board values/percentiles and qualification population into an indexed SQLite cache.
- Materialize the existing authoritative WOWY CSV into the same cache; WOWY values and percentiles are copied, not recalculated.
- Make primary and companion Big Board requests use the cache, including player_id filtering for companions.

Install
1. Replace the Website240 files with this package. Do not run any Fix 38/39 builder.
2. Stop the API.
3. From local_api run: python build_big_board_cache_v44.py
4. Start: python nba_per75_local_api.py
5. Build the frontend normally.

Expected
- Big Board API responses should be in the same low-hundreds-ms/local-cache range demonstrated by Fix 38.
- WOWY Offense/Defense/Net should return populated rows when the source CSV is present.
- Companion requests should use /api/v1/public/big-board?player_ids=... rather than the legacy 100000-row /api/v1/big-board?companion=1 path.
- Player Profiles are based on Fix 42 and are intentionally not re-architected.
