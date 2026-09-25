# Website254 — Create Your T75 Final Composition Refinement

## User-requested visual changes
- Make the bottom card fade visibly black and keep it short, rising only enough to support readable bottom copy.
- Enlarge all eight supplied player cutouts while preserving their complete visible source artwork.
- Keep players on the right side of each card, overlapping the large tier number slightly and occupying roughly half of the card.
- Remove artificial clipping/barriers so the large background tier numbers are not cut off.
- Preserve the user's original supplied player images; no AI-generated player artwork was introduced.

## Implementation
- `src/v13_final_corrections.css` adds the Website254 override layer.
- Card overflow is allowed so the number has no artificial inner clipping boundary.
- Player images use native aspect ratio with simultaneous max-width/max-height constraints, preventing head/arm/ball loss from `cover` or forced dimensions.
- A dedicated `::after` bottom fade provides the black readability gradient while remaining beneath the card copy.
