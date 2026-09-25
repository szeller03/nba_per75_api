# Website169 — canonical team source + defensive Four Factors ingestion

This build makes the team-season CSV the preferred Team analytics source and
adds recognition for defensive/opponent Four Factors fields.

Changes:
- Team-season/team-data files are prioritized over older generic files when
  the backend discovers its source.
- Added aliases for defensive/opponent TOV% and eFG% naming conventions,
  including Def/Defensive/Opp variants.
- Team analytics cache schema bumped v5 -> v6, forcing regeneration.
- No opponent metric is calculated from the team's own TOV% or eFG%; the
  backend only exposes a value when the source contains the corresponding
  defensive/opponent field.
- Existing Player Profiles, Explorer, Big Board, Compare, Create Your List,
  duplicate identity handling, and NEW SDI v4 are retained.
