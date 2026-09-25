# Website171 — actual Basketball-Reference defensive Four Factors ingestion

Website170 still depended on columns that were not present in the canonical
team-season CSV. The uploaded CSV has the Basketball-Reference Advanced Stats
table flattened with the Defense Four Factors values lost as blank separator
columns, so column aliases alone could never populate Opponent TOV% or Opponent
eFG%.

Website171 fixes this at the source-ingestion layer:

- The API now has a Basketball-Reference Advanced Stats fallback.
- For each missing team-season, it fetches the corresponding BRef league
  Advanced Stats table (or playoff Advanced Stats table).
- It parses the distinct Defense Four Factors group.
- The second eFG% and TOV% columns are stored as:
    opp_efgpct
    opp_tovpct
- Team names are normalized before merging back into the canonical team-season
  rows.
- A local cache `bref_team_defense_four_factors_v1.json` prevents repeated
  downloads after the first successful build.
- The team analytics cache version is bumped to v8.
- The standalone `precompute_team_analytics_v1.py` was updated with the same
  ingestion logic.
- Existing team statistics are untouched.
- No opponent statistic is inferred from the team's own eFG% or TOV%.

The first rebuild may take longer because missing season pages must be fetched
once. Subsequent API starts use the local defensive Four Factors cache.
