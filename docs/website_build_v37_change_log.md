# V37 — USG% Optional Source Fix

V36 assumed `USG%` existed in the playoff statistical input and crashed when
it did not.

V37 treats USG% as optional. If present, it is retained for a single-team
player-season; otherwise it is NaN.

TOV% remains derivable from the player's FGA, FTA, and TOV.

No identity decisions changed and no unsupported metric is fabricated.
