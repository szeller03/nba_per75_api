# V25 — Correct Team Evidence Source

## V24 problem

V24 assumed `player_data_v1_1/player_seasons_v1_1.csv` contained `Team`.
It does not.

The project's own website identity builder constructs the canonical player-season
universe from `Player_ID`, `Player`, `Season`, and `Season_Type`, while upstream
master processing explicitly relies on `Team` when resolving multi-team rows.

## V25 fix

V25 uses:

`data/nba_per75_master_dreb_v2.csv`

for regular-season team evidence and attaches the existing website `Player_ID`
through the canonical identity layer.

Team evidence is therefore:

- same Player_ID
- same regular-season Season
- same normalized Team

A collision is auto-resolved only when that evidence uniquely identifies one
candidate.

No fuzzy matching.
No silent guesses.
