# Website138 — Create Your T10 / T25 / T50 / T75

Added a dedicated Create Your T50 page with four list-depth modes.

## Candidate pools
- T10: 20 candidates
- T25: 45 candidates
- T50: 84 candidates
- T75: 114 candidates (the original master pool, with the T10/T25/T50 tiers
  cumulatively included)

## Interaction
- Users choose a list depth.
- Two player cards are shown at a time.
- Choosing a card records a pairwise preference.
- Matchups are selected adaptively and avoid unnecessary repeats.
- The active ranking is updated after every decision.
- The T50 mode has a 100-decision maximum.
- T10/T25/T75 use 35/55/125 maximums respectively.
- The page stops at the mode's decision cap and displays the requested list.
- Decisions are saved in localStorage independently for each mode.
- A Start Over control resets the selected mode.

## Headshots
The cards use the site's existing canonical player search data when available,
with the existing `/api/v1/players/{id}/headshot` endpoint as the fallback.

## Important
The T75 pool uses the remaining players from the previously supplied 114-player
master pool because no separate T75 additions were supplied yet.
