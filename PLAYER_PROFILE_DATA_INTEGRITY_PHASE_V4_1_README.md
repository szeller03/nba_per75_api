# Player Profile Data Integrity — Forensic Phase v4.1

This is the same forensic audit as v4, with a **Windows-safe Python source fix**.
The previous v4 package could fail before execution because a Windows path in a
Python docstring was interpreted as a `\N` Unicode escape.

## Install

Replace the v4 audit files in:

`NBA_Per75_Website241\local_api\`

with:

- `audit_player_profile_data_integrity_v4.py`
- `validate_player_profile_data_integrity_v4.py`

## Run

```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"

python local_api\audit_player_profile_data_integrity_v4.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
```

Then:

```powershell
python local_api\validate_player_profile_data_integrity_v4.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241\data\player_profile_data_integrity_forensic_report_v4.json"
```

v4.1 does not change the forensic methodology. It only fixes the Python
syntax/escaping problem and keeps the audit read-only.
