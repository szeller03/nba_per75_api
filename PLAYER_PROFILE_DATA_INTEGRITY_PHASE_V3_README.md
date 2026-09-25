# Player Profile Data Integrity Phase v3

This is the **data-integrity audit only**. It does not build a new website and
does not alter production data.

### Install

Place these two files in:

`NBA_Per75_Website241\local_api\`

- `audit_player_profile_data_integrity_v3.py`
- `validate_player_profile_data_integrity_v3.py`

### Run

```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
python local_api\audit_player_profile_data_integrity_v3.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
```

Then:

```powershell
python local_api\validate_player_profile_data_integrity_v3.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241\data\player_profile_data_integrity_report_v3.json"
```

### What changed from v2

v3 is evidence-first rather than assuming a generic identity rule.

It:
- prints actual schemas and key candidates;
- shows concrete duplicate samples for Master and Playoff SDI;
- resolves the exact known Regular/Playoff 5-Year Peak filenames;
- inspects the JSON structures;
- extracts Wilt PTS/75 values across available layers;
- checks Career qualification;
- checks numeric ranges;
- records the locked Route A architecture.

**Important:** duplicate rows are surfaced for review rather than automatically
treated as corruption, because the master/player-season architecture may contain
legitimate split/team rows.

The script is read-only except for:
`data\player_profile_data_integrity_report_v3.json`
