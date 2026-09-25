# NBA PER-75 Website — Player Profile Fix 50.7.1

## Purpose
Repair the Fix 50.7 Career SDI rebuild failure caused by duplicate columns when restoring legacy columns from the existing Career SDI CSV.

## Exact failure fixed
The 50.7 builder attempted to merge legacy columns that were already authoritative in the newly rebuilt frame. This caused pandas to reject duplicate `Player`, `WOWY_Offense`, `WOWY_Defense`, and `WOWY_Net` columns with `_x/_y` suffixes.

## 50.7.1 change
The builder now explicitly treats these as authoritative and does **not** restore them from the old CSV:

- Player_ID
- Player
- Career G / Career MP
- Qualified_Career
- all Career SDI category fields
- all category coverage fields
- SDI_v4 / SDI_v4_WOWY / Career_SDI_v4
- WOWY_Offense / WOWY_Defense / WOWY_Net

Only genuinely legacy/non-authoritative columns are merged back by Player_ID.

The canonical Career WOWY reconstruction, locked SDI v4 weights, lower-is-better percentile handling, TRB% derivation, and pre-write Rudy Gobert validation from Fix 50.7 are preserved.

## Run
From the website root:

```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
python local_api\build_career_sdi_v4_wowy_v2.py
```

The script will abort before replacing the live Career SDI CSV if Rudy Gobert is missing WOWY Offense, WOWY Defense, WOWY Net, or Career Impact & Value.

## Expected result
A successful build prints a JSON report including Rudy Gobert's six Career SDI category values and overall `SDI_v4_WOWY`, then writes:

`data\regular_career_sdi_v4_wowy_rts.csv`

