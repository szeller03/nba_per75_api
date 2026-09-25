# V23.1 — Master Schema Compatibility Fix

The V23 resolver assumed the regular-season master always exposed canonical
`Player_ID` and `Season` columns. The current master version does not expose
that exact pair, so V23.1 adds a safe fallback.

If the master lacks those fields, the resolver uses the existing identity
registry's `Available_Seasons` to build each canonical player's career-year
universe. Team evidence is then left unavailable rather than inferred.

If the master does expose a compatible Player_ID + Season pair, V23.1 uses
the full team/temporal evidence path.

No fuzzy matching or silent identity assignment is introduced.
