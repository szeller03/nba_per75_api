# Player Profile Data Integrity — Forensic Phase v4

This package is **audit-only**. It does not rebuild the website and does not
modify any source/cache data.

## Install

Copy these into:

`NBA_Per75_Website241\local_api\`

- `audit_player_profile_data_integrity_v4.py`
- `validate_player_profile_data_integrity_v4.py`

## Run

```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
python local_api\audit_player_profile_data_integrity_v4.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
```

Then optionally:

```powershell
python local_api\validate_player_profile_data_integrity_v4.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241\data\player_profile_data_integrity_forensic_report_v4.json"
```

## What v4 does

v4 follows the v3 result and goes one level deeper:

1. Uses `Player_ID + Season + Season_Type` for the Master forensic pass.
2. Prints **every full row** in each remaining Master duplicate group.
3. Prints **every full row** in each remaining Playoff SDI duplicate group.
4. Creates a flat duplicate CSV for easy inspection.
5. Extracts Wilt Chamberlain rows and PTS/75 values from every available CSV layer.
6. Checks the actual Regular and Playoff Peak JSON records for:
   - exactly five selected seasons;
   - maximum six-calendar-season span;
   - no two-year gap.
7. Reports the actual WOWY columns present in raw WOWY, Career SDI, and Regular SDI.
8. Preserves the distinction between Route A SDI and its companion percentile.

The validator deliberately leaves duplicate classification as REVIEW REQUIRED.
No duplicate is automatically deleted or rewritten.
