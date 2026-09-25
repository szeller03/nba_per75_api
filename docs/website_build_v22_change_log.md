# V22 — Basketball-Reference Playoff Identity Integration

V22 turns the 11,322 Basketball-Reference playoff player-team rows into a
canonical player-season source connected to the site's 4,896-player identity
registry.

## Input
- `data/nba_per75_playoffs_bref_v1.csv`
- `player_website_identity_v1/website_player_identity_v1.csv`
- `data/nba_per75_master_dreb_v2.csv`

## Resolution rules
1. Exact normalized B-Ref player name -> canonical Player_ID.
2. Conservative explicit aliases only when explicitly defined.
3. If multiple canonical players share a normalized name, career-year overlap
   is used only when exactly one candidate contains that playoff season.
4. Otherwise the row is retained as Ambiguous/Unmatched.
5. No fuzzy matching and no silent identity guesses.

## Consolidation
B-Ref player-team rows are consolidated into one canonical player-season row.
Additive totals are summed. Shooting percentages are recalculated from the
consolidated attempts. Missing historical statistics remain unavailable.

## Outputs
- `data/nba_per75_playoffs_player_season_v1.csv`
- `data/nba_per75_playoffs_identity_audit_v1.csv`
- `data/nba_per75_playoffs_unmatched_v1.csv`

## Website routing
The API now prefers the canonical player-season playoff source. In Playoffs
mode, profile seasons come from the playoff source rather than the
regular-season master. Playoff percentiles are intentionally not fabricated
yet; this is the identity/raw-statistics integration layer.
