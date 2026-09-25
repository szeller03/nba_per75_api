Website240 Performance Fix 38

Purpose: move regular-season Big Board population/qualification work out of the HTTP request path.

Files added/changed:
- local_api/public_data_layer.py: uses data/public/big_board_cache_v38.sqlite3 when present.
- local_api/build_big_board_cache_v38.py: one-time builder from the existing canonical public SQLite + eligibility databases.
- local_api/test_fix38_performance.py: direct API timing test.
- local_api/nba_per75_local_api.py: reports whether the v38 cache is available at startup.

No statistical values, SDI/WOWY methodology, qualification thresholds, peak methodology, or headshot hierarchy are changed.

One-time build:
1. Stop nba_per75_local_api.py.
2. From local_api run: python build_big_board_cache_v38.py
3. Restart: python nba_per75_local_api.py
4. In another terminal run: python test_fix38_performance.py

The cache is a compact indexed SQLite build artifact. The public request path does not calculate qualification or join the research tables when the cache is present.
