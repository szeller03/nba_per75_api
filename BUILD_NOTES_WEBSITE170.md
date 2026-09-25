# Website170 — Team defensive Four Factors ingestion

This is the data-generation fix, not another UI-only patch.

The existing `local_api/precompute_team_analytics_v1.py` previously extracted
only the offensive Four Factors from the canonical team-season CSV. It now:

- Detects explicit Opp/Defensive TOV% and eFG% fields.
- Detects Basketball-Reference flattened duplicate headers such as `TOV%.1`
  and `eFG%.1`, which are the defensive/opponent copies when a BRef Advanced
  Stats table is exported with duplicate Four-Factor headings.
- Includes `opp_tovpct` and `opp_efgpct` in the generated team analytics rows.
- Adds Opponent TOV% and Opponent eFG% to the generated statistic registry.
- Retains all existing Team metrics and calculations.
- Does not derive opponent metrics from the team's own values.
- The API team cache schema is bumped to v7 so stale team analytics cannot be
  reused.

The next API startup/precompute will regenerate the team analytics cache from
the canonical team-season source.
