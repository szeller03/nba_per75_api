# Player Profile Fix 50.6 — Canonical Career SDI Rebuild

This build follows the Career SDI methodology selected after the Gobert audit.

## Methodology

Career SDI is calculated as:

**career underlying values → career percentiles → locked SDI v4 category weights**

The rebuild does **not** average individual-season SDIs.

Career WOWY Offense, WOWY Defense, and WOWY Net are taken from the site's existing canonical career aggregation in `_build_regular_career_table()`. No new WOWY aggregation methodology is introduced.

## Locked top-level weights

- Scoring Volume: 20%
- Scoring Efficiency: 18%
- Creation & Playmaking: 18%
- Rebounding: 10.5%
- Defense: 20%
- Impact & Value: 13.5%

## What changes

`local_api/build_career_sdi_v4_wowy_v2.py` rebuilds:

`data/regular_career_sdi_v4_wowy_rts.csv`

for every player meeting the existing Career qualification rule (400 games + 10,000 minutes).

It also writes:

`data/SDI_V4_WOWY_CAREER_BUILD_REPORT_V2.json`

An existing Career SDI file is backed up as:

`data/regular_career_sdi_v4_wowy_rts.pre_50_6_backup.csv`

before replacement.

## Run

From the project root:

```text
python local_api/build_career_sdi_v4_wowy_v2.py
```

Restart the local API after the build so the Career SDI axes cache is warmed from the rebuilt file.

## Scope protection

This build does not change:

- individual-season SDI v4
- playoff SDI
- 5-Year Peak methodology
- Player Compare
- Big Board
- Explorer
- headshots
- Profile request/performance architecture
