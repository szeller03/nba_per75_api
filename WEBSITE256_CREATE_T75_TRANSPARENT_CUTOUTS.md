# Website256 — Create Your T75 transparent cutout integration

- Replaced the prior processed/white-background chooser artwork with the eight user-supplied transparent PNG cutouts.
- Cropped only transparent outer margins; player pixels were not edited.
- Rebuilt chooser number layer so multi-digit values use a glyph-sized, overflow-visible wrapper and are not clipped by an internal width barrier.
- Added a short black bottom gradient for readable chooser descriptions.
- Independently scaled each supplied player cutout while preserving its native aspect ratio and complete visible artwork.
- Kept player layer in front of the number and bottom copy above the fade.
