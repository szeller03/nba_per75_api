# Website267 — Create Your T75 List Output Visual Redesign

Built from Website266.

## Implemented
- T10 output changed to a compact premium share-card composition inspired by the supplied reference.
- Removed the visible white portrait tile treatment from T10 rows; headshots sit directly on the dark card.
- Enlarged T10 player names and tightened row heights to remove excess empty space.
- Larger outputs retain compact reference-board density but use open portrait treatment, stronger first-three-rank hierarchy, and non-clipping wrapped names.
- T25 now uses a two-column ranking layout.
- T50 and T75 now use three-column ranking layouts.
- Added a cinematic legacy/player wall at the bottom of T25/T50/T75 using the existing T50Headshot pipeline, keeping the player imagery data-driven and avoiding new generated artwork.
- Added split title hierarchy: `MY TOP X` / `PLAYERS OF ALL-TIME`.
- Preserved existing sharing, profile links, start-over behavior, and list-building logic.

## Validation
- App.jsx and CSS were edited from the Website266 source tree.
- ZIP integrity is verified after packaging.
- A full production Vite build was not claimed because recent project environments have not consistently had dependencies available.
