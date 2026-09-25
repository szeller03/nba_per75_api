# Player Profile Fix 50.6.3 — Career SDI Builder Post-Write Diagnostic Repair

This is a repair to Fix 50.6.2. It does not change the Career SDI methodology or weights.

## Repair
The builder successfully constructs the rebuilt Career SDI DataFrame, but its final Rudy Gobert diagnostic assumed a `Player` column existed under that exact spelling. In some pandas/canonical-table variants the rebuilt frame may not expose that display-name column in the expected form, causing a post-write `KeyError: 'Player'` after the rebuild itself.

The diagnostic now resolves display-name aliases safely (`Player`, `Player_Name`, `player_name`, `Name`) and does not turn a completed rebuild into an exception.

## Run
From the project root:

```powershell
python local_api/build_career_sdi_v4_wowy_v2.py
```

The script keeps the same canonical Career SDI v4 methodology and writes the normal career SDI output plus its build report.
