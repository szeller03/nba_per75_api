# V23.2 — Identity Registry Variable Fix

V23.1's fallback correctly recognized that the current regular-season master
does not expose the expected Player_ID + Season schema, but the fallback
contained a variable-name typo (`identity` instead of the loaded `ident`
DataFrame). V23.2 fixes that typo.

No methodology changed:
- no fuzzy matching
- no silent guesses
- Available_Seasons remains the safe fallback for career-year evidence
- team evidence is used only when the master exposes usable player/team/season
  fields
