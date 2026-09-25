# Website247 — User Feedback Patch

## Player Profiles
- Expanded configurable spider chart geometry after opening the configuration view: larger SVG/radar and a larger label radius.
- Increased configurable spider surrounding label typography to 15px, weight 900, with stronger contrast.
- Increased configurable radar panel height and allowed overflow so larger labels remain visible.

## Comparison
- Increased player portrait image scale inside the existing square avatar frame so the actual player fills substantially more of the box.
- Preserved the existing comparison card and player-headshot source; no new image source was introduced.

## Teams
- Kept team logos at natural brightness (no blend-mode/filter darkening).
- For season-specific rows, prefer the existing historical team-logo source first, followed by the existing direct/current/ESPN/canonical fallbacks. This is intended to avoid opaque white logo tiles while preserving the established historical source hierarchy.
- Existing positive NRtg/ORtg/DRtg `+` formatting remains in place.

## Create Your T75
- No pool-icon player artwork was added in this build. The user wants to select the specific non-AI player images before those assets are applied.
