# V28 — Canonical Playoff Stats Input Fix

V27's possession calculation was sound, but its implementation attempted to
merge raw B-Ref totals with the canonical playoff identity layer on Player_ID.
The raw B-Ref source does not need to contain canonical website Player_ID
values.

V28 uses `nba_per75_playoffs_player_season_v4.csv` directly. That file already
contains the resolved Player_ID, player, season, team, and consolidated B-Ref
counting totals.

No identity decisions are changed.
No fuzzy matching.
No silent identity guesses.
