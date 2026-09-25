# NBA PER-75 Website V55 — Playoff Profile Season Mapping Repair

## Primary fix
The finalized playoff season data stores seasons as starting-year integers (e.g. `1985`, `1986`), while the player-profile UI uses canonical season labels (`1984-85`, `1985-86`). V54 matched these representations literally, so playoff profile requests could return a player profile shell without matching the selected playoff row or its percentiles.

V55 normalizes playoff season labels consistently for:
- Player Profile season lists
- Playoff raw-stat row selection
- Playoff percentile row selection
- Playoff spider season selection

The underlying playoff dataset remains unchanged.

## Qualification behavior
Unqualified playoff seasons remain viewable with raw playoff statistics, but their Season/Era/Historical percentile values and percentile spider are correctly unavailable. Qualified playoff seasons expose the full 46-stat percentile set and spider data.

## Career
Playoff Career remains qualified using the established threshold of >=50 games AND >=1,500 minutes. Regular-season Career remains >=400 games AND >=10,000 minutes.
