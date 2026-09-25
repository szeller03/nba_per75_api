# V30 — Canonical Player_ID Merge Fix

V29 correctly reconstructed B-Ref player-team rows, but the merge produced
`Player_ID_bref` and `Player_ID_canonical` because the raw B-Ref source already
contains a Player_ID column.

V30 explicitly selects `Player_ID_canonical` as the authoritative identity
after the join.

No new identity matching is performed.
No fuzzy matching.
No silent guesses.
