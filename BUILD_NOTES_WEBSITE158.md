# Website158 — Big Board performance optimization

The 20-second first-load path was traced to the canonical long-format percentile
table and qualification gate being hydrated on the first Big Board request.

Optimizations:
1. Cache the resolved canonical percentile CSV path so ROOT.rglob() is not
   repeated.
2. Load only the columns actually needed by the Big Board/profile percentile
   path (identity, season, statistic, value, and percentile columns), with a
   full-table fallback for unexpected schemas.
3. Load the master season table once.
4. Warm the PTS/75 BRef eligibility gate at API startup.
5. Warm the exact default PTS/75 Historical Big Board at API startup.

The frontend's statistic remains PTS/75 and the existing ranking/qualification
logic is unchanged. The expensive first-request work is moved to API startup,
so clicking Big Board should return the already-warmed default dataset.
