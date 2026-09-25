# V22.2 — Playoff Identity Review Layer

The V22.1 run resolved 9,466 of 11,322 raw B-Ref rows, with 1,567
ambiguous and 289 unmatched. V22.2 adds a review-oriented resolver that
re-runs the same deterministic rules and produces grouped candidate review
data.

It does not introduce fuzzy matching or guesses.

Outputs:
- `nba_per75_playoffs_player_season_v2.csv`
- `nba_per75_playoffs_identity_audit_v2.csv`
- `nba_per75_playoffs_unresolved_review_v2.csv`
- `nba_per75_playoffs_identity_candidate_groups_v1.csv`

The candidate-group file is intended to make the remaining ambiguous identities
easy to inspect before any additional aliases are approved.
