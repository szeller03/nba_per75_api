Website240 — Performance Fix 37
================================

Purpose
-------
Fix 36 successfully reduced Career spider HTTP latency to roughly 0.15–0.18s.
The next bottleneck visible in the Fix 36 browser log is Big Board delivery:
multiple public Big Board requests still take roughly 1–2 seconds each, while
companion-stat requests were still falling through to the legacy API path.

Changes
-------
1. public_data_layer.py now keeps a bounded in-memory cache for small, repeated
   Big Board query results. SQLite remains authoritative; this only avoids
   repeating identical indexed reads during a browsing session.
2. Added optimize_public_sqlite_v37.py to add composite eligibility lookup
   indexes. This does not change eligibility rules or statistical values.
3. Added test_fix37_performance.py to compare first and repeat public Big Board
   request times.
4. Existing Fix 36 Career spider architecture is unchanged.
5. Existing SDI/WOWY, qualification, peak, headshot, and statistical
   methodology is unchanged.

Installation
------------
Copy the files from this patch into the existing Website240 folder, replacing
local_api/public_data_layer.py and adding the two new scripts.

One-time SQLite optimization
-----------------------------
STOP the API first, then from Website240/local_api run:

    python optimize_public_sqlite_v37.py

Then restart:

    python nba_per75_local_api.py

Validation
----------
With the API running in one PowerShell window, run in another:

    python test_fix37_performance.py

The repeat time should be substantially lower than the first time for each
identical query. The more important next measurement is the first-time Big
Board request after the SQLite indexes are installed.
