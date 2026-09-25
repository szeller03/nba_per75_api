# Phase 3 — Playoff SDI v4 Rebuild

This is the next production fix after the playoff percentile rebuild.

## Run

From the Website241 root:

```powershell
python local_api\rebuild_playoff_sdi_v4.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
python local_api\validate_playoff_sdi_v4.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
```

## What it does

It rebuilds:

`local_api\cache\playoff_sdi_v4_player_seasons.csv`

from the corrected playoff percentile table and the Master playoff records.

Locked playoff qualification:

- 4+ games
- 75+ minutes

Locked SDI v4 weights are encoded in the script, including the current Defense
60/40 block/steal activity split.

A pre-existing playoff SDI cache is backed up before replacement.

## What it does NOT touch

- regular-season SDI
- Career SDI
- regular 5-Year Peak
- playoff 5-Year Peak
- Master
- percentile CSV

If the corrected percentile file cannot supply a required statistic, the row is
not silently assigned a guessed value. The script reports those rows for review.

## Important

Run Phase 2 first. Phase 3 assumes the playoff percentile rebuild is already in
place.
