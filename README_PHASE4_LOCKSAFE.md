# Phase 4 — Lock-Safe Player Profile Playoff SDI Integration

The first Phase 4 installer attempted to replace `nba_per75_local_api.py`.
Windows can prevent that when the file is open by Python, an IDE, OneDrive,
antivirus, or another process.

**Use this lock-safe package instead. It does not overwrite the original API.**

## Run

From the Website241 root:

```powershell
python local_api\run_phase4_api.py "C:/Users/szell/OneDrive/Desktop/NBA_Per75_Website241"
```

This launches the Phase 4 API from:

```text
local_api\nba_per75_local_api_phase4.py
```

The original:

```text
local_api\nba_per75_local_api.py
```

is left untouched.

## Important

Stop the old API before launching Phase 4, because both normally use port 8000.

If port 8000 is still occupied, in PowerShell:

```powershell
Get-Process python,pythonw -ErrorAction SilentlyContinue | Stop-Process -Force
```

Then launch Phase 4 again.

## Validation

The original Phase 4 validator can still be run:

```powershell
python local_api\validate_phase4_playoff_profile_sdi.py "C:/Users/szell/OneDrive/Desktop/NBA_Per75_Website241"
```

## What this fixes

Phase 4 connects playoff SDI dimensions to the existing Player Profile API
response, including playoff Career/season SDI fields and category axes.

It does not modify regular-season SDI, Career regular-season SDI, or peak data.

## After launch

Open the Player Profile and switch to **Playoffs**. Kareem is the primary
validation case: the playoff SDI category boxes should no longer be NQ if the
underlying playoff SDI data is available to the API.
