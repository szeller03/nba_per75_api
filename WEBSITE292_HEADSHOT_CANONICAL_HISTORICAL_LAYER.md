# WEBSITE292 — Canonical Historical Headshot Layer

This build replaces the unusable NBA CDN population at the source-selection layer.

- 2,860 records: NBA CDN returned the byte-identical generic placeholder.
- 197 records: the authoritative registry has no NBA CDN URL / Player ID.
- Total historical fallback population: 3,057 player records.
- Fallback source: Basketball-Reference player photo URLs already present in the project's source-resolution layer.
- The raw source photo is rendered directly; the Website290 destructive background-removal/canvas normalization path is not used for these records.
- A `multiply` visual treatment suppresses white photo backgrounds without modifying the source image pixels, avoiding the prior bad-crop artifacts.

Source audit: HEADSHOT_VISUAL_AUDIT_V3 found 4,699 downloaded NBA CDN records, 2,860 exact generic placeholders, 1,839 non-placeholder photos, and 197 players with no NBA CDN local image.

Important: this is a source-selection build, not a claim that every Basketball-Reference photo has been independently identity-reviewed at the pixel level. The source mapping is deterministic and comes from the project's existing B-Ref resolution candidates.
