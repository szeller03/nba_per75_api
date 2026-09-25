# Website240 — PNG + NBA CDN Headshot Build

Apply this runtime patch and all three headshot asset ZIPs over the existing Website239 site.

## Install
1. Extract `Website240_RUNTIME_PATCH_PNG_CDN_ONLY.zip` into the Website239 root and allow replacement of existing files.
2. Extract `Website240_HEADSHOTS_PART_1.zip`, `Website240_HEADSHOTS_PART_2.zip`, and `Website240_HEADSHOTS_PART_3.zip` into the same Website root, allowing the PNG files to merge into `public/player_headshots_final_v1/`.
3. Start the existing local API normally.
4. Hard-refresh the browser.

## Active headshot sources
- 584 shipped historical/manual PNGs.
- Official NBA CDN for players without a shipped local PNG.
- No Basketball-Reference player headshots.
- No JPG/JPEG player-headshot files.

Historical/manual PNGs are canonical and take priority over NBA CDN values wherever a local PNG exists.
