# Player Profile Data Integrity Phase v2

This is a **data-integrity-only** package. It does not create or replace a website.

## Put these two files in Website241

- `local_api\audit_player_profile_data_integrity.py`
- `local_api\validate_player_profile_data_integrity.py`

## Run

From Website241:

```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
python local_api\audit_player_profile_data_integrity.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
```

Then:

```powershell
python local_api\validate_player_profile_data_integrity.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241\data\player_profile_data_integrity_report_v2.json"
```

## v2 fixes

The first audit incorrectly treated:
- Player + Season as unique even when Season_Type exists.
- Player + Season as unique in the long percentile table, where Statistic is also part of the key.
- The authority-check JSON as the regular peak dataset.
- Playoff SDI as requiring a literal `Season` column.

v2 uses schema-aware identity keys and resolves the actual peak dataset.

The audit is read-only except for its report JSON.
