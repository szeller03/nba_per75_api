# Phase 5B — Player Profile State Cleanup

Targeted UI-only cleanup built from the known-good Phase 4/5A Player Profile.

## Changes
- Removes the brief Career NQ flash while the Career bundle is still loading. NQ is shown only after a Career bundle is actually available and fails the applicable qualification rule.
- Stops clearing the individual season rows every time the profile context changes. Individual season rows therefore remain visible while switching Career / Regular Season / Playoffs / 5-Year Peak.
- Leaves the API, headshots, SDI calculations, percentile calculations, playoff 5-Year Peak cache, and request deduplication untouched.

## Installation
Replace only:
`src/App.jsx`

Do not replace local_api or headshot assets.
