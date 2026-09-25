NBA PER-75 — B-REF OFFENSIVE FOUR FACTORS OFFLINE RECOVERY v120

Scope: Local API only

This package uses the uploaded Basketball-Reference season HTML cache. It does NOT make network requests.

Extracted ONLY:
- Offensive eFG%
- Offensive TOV%

Not touched:
- FTr
- Opponent eFG%
- Opponent TOV%
- Any other team Four Factors field

Source table:
Basketball-Reference season summary -> Advanced Stats -> Offense Four Factors.

The extractor preserves the two-level table headers so the Offensive eFG% / TOV% fields are read from
"Offense Four Factors", not the adjacent Defense Four Factors columns.

The cache contains 1952 through 2026 season-summary HTML pages. Some early historical pages do not expose
both offensive fields in the B-Ref table; those rows are intentionally omitted rather than calculated or guessed.

Files:
- extract_bref_offensive_ff.py  : offline extractor
- bref_offensive_four_factors_v1.json : extracted season/team values
- bref_offensive_four_factors_v1.csv  : flat audit output

No CSV team-master file is used as a source.
