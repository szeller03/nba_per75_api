# Website284 — Alternate Headshot Population

This pass populates the 197 player records without an NBA CDN headshot URL with a Basketball-Reference alternate candidate URL derived from the standard Basketball-Reference player image slug convention.

These alternate URLs are explicitly marked `alternate_candidate` / `unverified`; they are not represented as manually identity-verified. The NBA CDN remains the primary source for all players that already have one.

- Records populated: 197

- Primary-source records untouched: all records that already had a headshot URL

- Dedicated mapping: `player_headshots_final_v1/alternate_headshot_mappings_v1.csv`


## Source basis

The Basketball Reference player-photo JSON used by the BBGM-NBA-Info repository maps historical players to Basketball-Reference image URLs using the same `/req/0/images/players/<slug>.jpg` pattern. This build uses that alternate source convention for missing NBA CDN records.
