# V20 — Unified Career, Full Season Universe, and Playoff Source

## Big Board
- Career is a scope only.
- Career no longer appears as a Season option or Percentile Context option.
- Single-season filters are chronologically ordered.
- Season labels correctly roll `YY=00` into the next century.
- Career statistic values are sourced from the full master/player-season layer
  with a fallback to the raw-value fields of the canonical percentile source.
- Career percentiles are calculated from career values, subject to the existing
  qualification-population gate.
- Player rows route through React Router to `/players/{player_id}`.

## Profiles
- Full master season universe controls season availability.
- Non-qualified seasons are retained.
- Raw statistics are shown even where percentile rows do not exist.
- Career raw statistics are shown independently from percentile qualification.
- Career spider/context endpoints are supported.
- Percentile spider is not fabricated for an unqualified season.

## Playoffs
- Separate Regular Season / Playoffs profile mode.
- Playoff source discovery searches the master for a SeasonType field and then
  searches the NBA_Per75 tree for dedicated playoff/postseason CSVs.
- Added a source builder using NBA Stats LeagueDashPlayerStats with
  SeasonType=Playoffs. The source is kept separate from the regular-season
  master and requires a user-side run to populate.

No regular-season master or analytical source was overwritten.
