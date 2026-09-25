# Player Profile Data Integrity Phase

This package is **not a new website build**. It is the next data-integrity phase only.

## Files

`local_api/audit_player_profile_data_integrity.py`
- Read-only audit of the existing Website241 data layer.
- Discovers the relevant CSV/JSON files automatically.
- Checks identity duplication, missing fields, numeric ranges, career qualification, 5-Year Peak metadata, and named-player coverage.
- Produces `data/player_profile_data_integrity_report.json`.

`local_api/validate_player_profile_data_integrity.py`
- Validates the generated report.
- Does not modify source data.

## Run

From the existing Website241 root:

    cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"

    python local_api\audit_player_profile_data_integrity.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"

Then:

    python local_api\validate_player_profile_data_integrity.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241\data\player_profile_data_integrity_report.json"

## Important

This phase intentionally does **not**:
- change SDI values
- replace Route A with Route B
- change Player Profile UI
- overwrite headshots
- rebuild the whole website
- make a new website directory

The next data work is to use the report to resolve any actual integrity failures before the Player Profile redesign.
