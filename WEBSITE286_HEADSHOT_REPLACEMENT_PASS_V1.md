# Website286 — Headshot Replacement Pass v1

Start: Website285.

## Changes
- Confirmed 2,860 NBA CDN records are the repeated generic placeholder/silhouette image from the supplied image bundle.
- Retained the 1,839 confirmed non-placeholder NBA CDN images.
- Swapped only the 2,860 definite placeholder records in the canonical headshot registries to a Basketball-Reference fallback candidate URL.
- Preserved the 197 existing Basketball-Reference alternate records.
- Added `data/headshot_replacement_candidates_v1.csv` with original URL, primary replacement candidate, and the full candidate chain.
- Added `data/headshot_placeholder_player_ids_v1.json` and `data/headshot_replacement_summary_v1.json` for traceability.
- Updated the frontend headshot components so failed Basketball-Reference candidates automatically advance through multiple historically compatible player-ID candidates before falling back to initials.
- Updated the Players search results to use the same headshot fallback component.
- No statistics, SDI, peaks, or eligibility calculations were changed.

## Audit status
The replacement URLs are source-backed candidates, not visual identity certification. The next headshot review should spot-check the alternate-source population and replace any candidate that is unavailable or visibly mismatched.
