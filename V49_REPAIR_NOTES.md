# NBA PER-75 Website V49 — Performance & Display Name Repair

## Changes
- Public-facing player names should no longer display historical `*` markers.
- Underlying source/master data is intentionally left unchanged.
- Era Average remains available with the V48 qualification methodology:
  - Regular season: >=40% era participation, >=250 games, >=6,000 minutes.
  - Playoffs: >=40% era participation, >=40 games, >=1,250 minutes.
- V49 preserves the V48 career qualification fixes and playoff career thresholds.
- Statistical Dominance Index is intentionally unchanged.

## Validation
After starting the API and frontend:
1. Verify Big Board names such as historical players no longer show `*`.
2. Test Era Average for several eras and statistics.
3. Test Player Profile names and search results for the same cleanup.
4. Test the spider chart across season/career and regular-season/playoff contexts.
