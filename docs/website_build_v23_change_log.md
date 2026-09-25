# V23 — Playoff Team/Temporal Identity Resolver

V23 adds a deterministic evidence layer for unresolved Basketball-Reference
playoff identities.

## Evidence
- Exact normalized B-Ref name.
- Explicit aliases only when approved.
- Regular-season career-year overlap.
- Same player + same season + same team evidence.
- Adjacent-season career presence.
- Adjacent-season team continuity.

## Resolution policy
A name collision is auto-resolved only when exactly one candidate has strong
same-team + exact-year evidence. Otherwise the row remains ambiguous.

The decision audit records candidate IDs, scores, team evidence, career-year
evidence, adjacent-season evidence, and the reason for the decision.

No fuzzy matching or probabilistic identity assignment is used.

## Outputs
- `nba_per75_playoffs_player_season_v3.csv`
- `nba_per75_playoffs_identity_audit_v3.csv`
- `nba_per75_playoffs_identity_decisions_v3.csv`
- `nba_per75_playoffs_unresolved_review_v3.csv`
- `nba_per75_playoffs_identity_candidate_groups_v2.csv`

The regular-season master is read-only.
