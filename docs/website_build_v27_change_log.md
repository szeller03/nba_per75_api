# V27 — Remove B-Ref /per_poss Dependency

V26 was blocked at 1987 because Basketball-Reference returned HTTP 429 for
`/playoffs/NBA_YYYY_per_poss.html`.

V27 avoids those requests entirely.

For 1974-2026, player possessions are estimated from the B-Ref totals source
already downloaded for all 75 seasons. Team possessions are calculated from
team-summed player totals, and player possessions are allocated by the player's
share of team minutes.

This makes the playoff statistical layer complete from the same B-Ref totals
source used for identity resolution.

The methodology is clearly labeled as a derived estimate. It does not
pretend to reproduce B-Ref's proprietary/displayed Per-100 table.

No identity decisions are changed.
No fuzzy matching.
No silent identity guesses.
