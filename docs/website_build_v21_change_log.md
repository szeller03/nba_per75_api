# V21 — Basketball-Reference Canonical Playoff Source

## Source decision
Basketball-Reference is now the sole canonical playoff raw source for 1952-2026.
The NBA Stats playoff CSV generated during V20 is not part of the final
architecture.

## Builder
`analysis/build_bref_playoff_source_v1.py`

It requests:
`https://www.basketball-reference.com/playoffs/NBA_YYYY_totals.html`

for every season from 1952 through the requested endpoint (default 2026).

The builder handles Basketball-Reference tables that are embedded inside HTML
comments and extracts the Player Totals table.

## Data policy
- Totals pages are canonical raw input.
- Missing historical statistics remain missing; they are never converted to 0.
- Player/team rows are preserved, including separate team rows for players
  who played for multiple teams during a postseason.
- Player IDs are left blank at the raw-source stage rather than guessed.
- PER-75, playoff percentiles, qualification, career aggregation, and spiders
  are separate analytical layers.

## Output
`C:\Users\szell\OneDrive\Desktop\NBA_Per75\data\nba_per75_playoffs_bref_v1.csv`

## Validation
`analysis/validate_bref_playoff_source_v1.py`
checks requested coverage, required columns, season type, and missing seasons.

Basketball-Reference's 1952 playoff summary demonstrates that the historical
playoff pages exist and expose playoff leaders and historical series data.
Its modern 2026 playoff totals page exposes the player totals table with the
modern shooting/statistical columns.
