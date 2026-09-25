# V39 — Playoff Website/API Integration

V39 connects the finalized playoff 46-stat and percentile outputs to the
existing website.

Player profiles:
- Playoff Season and Playoff Career are available in the Season selector.
- Playoff statistics display actual values.
- Playoff percentiles display alongside those values.
- Season / Era / Historical contexts are supported.
- Career uses its own Career percentile context.
- Non-qualified seasons remain visible with percentile values omitted.
- Dominance, Context, and custom 46-stat spiders use playoff percentile data.

Big Board:
- Added a Regular Season / Playoffs dataset selector.
- Playoff single-season board uses playoff Season/Era/Historical percentiles.
- Playoff Career board uses playoff Career percentiles.
- Existing player-row links continue to route to `/players/:playerId`.

API:
- `/players/:id/profile?season_type=Playoffs`
- `/players/:id/spider?season_type=Playoffs`
- `/players/:id/context?season_type=Playoffs`
- `/big-board?season_type=Playoffs`

No identity decisions were changed.
No regular-season source data were overwritten.
No unsupported playoff statistics were fabricated.
