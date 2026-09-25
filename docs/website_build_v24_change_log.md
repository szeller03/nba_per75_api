# V24 — Canonical Regular-Season Team Evidence

V24 replaces the unusable master-schema team evidence path with the project's
actual canonical player-season source:

`NBA_Per75/player_data_v1_1/player_seasons_v1_1.csv`

The existing project code identifies this as the canonical player-season layer,
with Player_ID, Player, Season, Season_Type, and player-season data. The
identity resolver now uses its regular-season Team values as the authoritative
team-history evidence.

A playoff name collision is automatically resolved through team evidence only
when exactly one canonical candidate has both:
- the same season; and
- the same normalized team.

Adjacent-season team continuity remains audit evidence, not an automatic tie
breaker by itself.

No fuzzy matching and no silent guessing are used.
