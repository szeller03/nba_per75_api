# WEBSITE272 — Create Your Top 75 card tint + naming

- Renamed the user-facing navigation/landing label from “Create Your T75” to “Create Your Top 75”.
- Added a restrained gold-tinted treatment to the direct player-pool cards.
- Gold treatment applies to the card surfaces, hover state, selected state, and photo area while preserving the existing dark cinematic palette.
- Increased direct-pool player-name size slightly to reinforce the card identity.
- No data logic or selection behavior was changed.

## Community consensus feasibility
A true cross-user consensus list is feasible, but it requires a shared persistence layer. The current local API is read-only (`GET` routes) and does not currently provide a `POST` submission endpoint/database for collecting anonymous user-created lists. This build therefore does **not** fabricate a consensus score or present same-browser data as a community consensus.

Recommended production architecture when the site has a shared backend:
1. Anonymous submission endpoint accepts a completed T10/T25/T50/T75 list and method metadata.
2. Server stores a normalized player order for each submission.
3. Consensus rank is calculated from aggregate placements (optionally with minimum submission counts).
4. Create Your Top 75 can display “Community Consensus” separately from the user's personal list.
