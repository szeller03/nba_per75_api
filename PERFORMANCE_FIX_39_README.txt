Website240 Performance Fix 39

Fix 39 corrects the Big Board precomputed cache for WOWY.

IMPORTANT: Fix 38 returned 0 WOWY rows because its generic percentile-table builder did not contain the authoritative WOWY statistic rows. Fix 39 reads the existing cache/player_wowy_statistics_v1.csv directly and uses its WOWY values and percentiles. PER75_Qualified remains the population gate. No WOWY methodology is recalculated or replaced.

1. Stop the API.
2. From local_api run:
   python build_big_board_cache_v38.py
   (The filename is retained for compatibility; it now builds cache version 39.)
3. Start the API:
   python nba_per75_local_api.py
4. Test:
   python test_fix39_performance.py

Expected WOWY rows should be > 0 for Offense, Defense, and Net.
