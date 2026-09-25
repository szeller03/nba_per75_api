# HEADSHOT AUDIT V2 — Website285

## Scope
Automated structural audit of the 4,896-player headshot registry used by Website284.

## Results
- Total player records: 4,896
- NBA CDN records: 4,699
- NBA CDN URL structure failures: 0
- NBA CDN Player-ID / URL-ID mismatches: 0
- Basketball-Reference alternate records: 197
- Alternate URLs missing: 0
- Shared NBA CDN URL groups: 164
- NBA CDN records still requiring visual identity/photo review: 4,646

## What this audit establishes
Every existing NBA CDN record has a syntactically valid NBA headshot URL and its numeric URL ID matches the registry's NBA_Player_ID. All 197 alternate records have a populated Basketball-Reference URL.

## Limitation
This environment cannot directly fetch the remote image binaries, so this pass cannot safely certify the image pixels as the correct player or determine whether a photo is an active-playing image. The 4,646 candidates therefore remain unverified rather than being falsely marked verified.

## Files
- `nba_cdn_visual_review_queue.csv`: all 4,646 unverified NBA CDN candidates.
- `shared_headshot_url_rows.csv`: all rows participating in shared URL groups.
- `alternate_headshot_rows.csv`: all 197 alternate mappings.
- `nba_cdn_structural_exceptions.csv`: structural exceptions (expected to be empty).
