NBA PER-75 — Team Four Factors scraper v3

Purpose:
- Resume the Basketball-Reference Four Factors cache without blocking on long 429 waits.
- Successful seasons are preserved.
- A 429 no longer triggers 30/60/120/240/300-second retries.
- On the first 429, the sweep saves its progress and stops immediately.
- Rerun the same command later to resume from the first missing season.

Run from local_api:
    python precompute_team_four_factors_v2.py

A 429 will now produce:
    RATE LIMITED ...
    Stopping sweep now. No 300-second wait and no repeated 429 retries.

This intentionally avoids hammering Basketball-Reference while it is rate-limiting the client.
