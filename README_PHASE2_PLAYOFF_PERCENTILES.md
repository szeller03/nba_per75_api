# Phase 2 — Playoff Percentile Rebuild

This is the **next actual fix** after the Phase 1 identity layer.

It rebuilds playoff percentile values from the master data using a separate
qualified playoff population.

Locked qualification:
- at least 4 playoff games
- at least 75 playoff minutes

Lower-is-better handling:
- TOV/75
- TOV%

Regular-season percentile rows are preserved.

## Run

First run Phase 1 so the identity collision report exists:

```powershell
python local_api\build_canonical_player_identity_v1.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
```

Then run:

```powershell
python local_api\rebuild_playoff_percentiles_v1.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
python local_api\validate_playoff_percentiles_v1.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
```

## Safety

The existing percentile CSV is backed up before replacement.

The rebuild does not rebuild Career SDI, Regular 5-Year Peak, or Playoff SDI.
Those come after playoff percentiles are corrected.

If a statistic in the existing percentile table cannot be matched to a master
numeric column, it is skipped and reported rather than guessed.
