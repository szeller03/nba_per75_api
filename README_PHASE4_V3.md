# Phase 4 V3 — Actual Playoff Profile Fix

The previous Phase 4 build exposed SDI fields but did not fix the underlying
Profile percentile contract. This V3 rebuilds the playoff Profile response
from the authoritative playoff 46-stat layer.

## The concrete problems fixed

1. The playoff profile now returns:
   - Season_Percentile
   - Era_Percentile
   - Historical_Percentile
   - Career_Percentile for Career
   - Percentile
   - percentile
   - Pctl
   - pctl
   - Percentile_Value

2. The playoff spider/category axes are calculated from the active playoff
   percentile family.

3. Route-A playoff SDI is exposed through all common Profile field aliases:
   - SDI_v4_Playoffs
   - SDI_v4
   - SDI_v4_WOWY
   - sdi_v4
   - Career_SDI_v4 / Career_SDI_v4_WOWY for Career

4. Single-season playoff percentile qualification is locked to:
   G >= 4 and MP >= 75.

5. The regular-season API file is not overwritten.

## Run

Stop the old API first.

Then from Website241 root:

```powershell
python local_api\run_phase4_v3_api.py "C:/Users/szell/OneDrive/Desktop/NBA_Per75_Website241"
```

Validate syntax:

```powershell
python local_api\validate_phase4_v3.py "C:/Users/szell/OneDrive/Desktop/NBA_Per75_Website241"
```

## Kareem test

Open Kareem's Player Profile and select Playoffs.

Expected:
- playoff season percentile values populate
- Career playoff percentile values populate
- six playoff SDI category axes populate where evidence exists
- playoff SDI is no longer NQ when the underlying qualified data exists

If the visible page still shows NQ after this V3 API is running, the remaining
problem is definitively in the frontend renderer's field mapping, not the
playoff data/API response.
