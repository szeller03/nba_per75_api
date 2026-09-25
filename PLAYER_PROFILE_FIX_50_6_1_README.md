# Player Profile Fix 50.6.1 — Career SDI Builder Repair

This is a repair of Fix 50.6. It does not change the locked Career SDI methodology.

## Repair
The canonical Career table in some Website240 builds does not materialize `TRB_pct`,
although the canonical regular-season player-season profile layer contains it. The
builder now:

1. prefers a direct canonical `TRB_pct`/`TRB%` career field when available;
2. otherwise derives Career `TRB_pct` from the canonical regular-season player-season
   `TRB_pct` values using MP-weighted aggregation;
3. fails clearly only if neither canonical source is available.

The builder then performs the same career percentile -> locked SDI v4 weighting used by Fix 50.6.

## Run
From the project root:

```powershell
python local_api/build_career_sdi_v4_wowy_v2.py
```

Then restart the local API and inspect the generated build report.
