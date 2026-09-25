# V29 — Recover B-Ref Team Rows for Playoff Possession Calculation

V28 correctly switched to the canonical playoff identity layer, but that
layer intentionally lacks Team. V29 reconstructs the player-team rows by
joining the raw B-Ref totals source to the canonical v4 identity output on
normalized B-Ref player name + season.

This is not an identity resolver and makes no new identity decisions.

The raw B-Ref Team and counting totals are then used for team possession
estimation:
FGA + 0.44*FTA - ORB + TOV

Player possessions:
team possessions * player MP / team MP

Per-75:
stat / player possessions * 75

No fuzzy matching.
No silent guesses.
