# Website255 — Create Your T75 visual rebuild

## Purpose
Final cleanup pass for the Create Your T75 chooser based on the supplied visual reference and the user's eight supplied player cutouts.

## Visual changes
- Replaced the accumulated chooser-card overrides with one final CSS layer.
- Large T10/T25/T50/T75 glyphs are standalone gradient text with no rectangular gradient/background container.
- Number glyphs remain visible without an artificial width barrier and sit behind the player artwork.
- Added a short, clearly visible black bottom fade rising from the card edge to support the bottom description.
- Restored and enlarged the bottom descriptions.
- Player artwork is rendered using preserved native aspect ratio with no `object-fit: cover` crop and explicit per-player max dimensions.
- Player cutouts are anchored to the lower-right and overlap the large number layer.
- Kept Head-to-Head red and Build Your List gold.

## Supplied artwork
The production assets in `public/create-t75/` were replaced with the eight individually supplied PNGs. Their white backgrounds were removed only where connected to the image boundary, preserving interior white details such as uniforms/signs. No AI-generated player artwork was introduced.

Mapping:
- lebron.png = Players (1).png
- garnett.png = Players (2).png
- shai.png = Players (3).png
- iverson.png = Players (4).png
- jordan.png = Players (5).png
- wilt.png = Players (6).png
- west.png = Players (7).png
- westbrook.png = Players (8).png

## Functional scope
No ranking/data logic was changed. The existing Head-to-Head and direct player-pool builder flows remain intact.

## Validation
- Verified all eight supplied image files were processed and present.
- Verified App.jsx remained unchanged in this visual-only pass.
- Dependency installation was attempted offline but the npm cache did not contain all required packages, so a Vite production build was not available in this environment.
