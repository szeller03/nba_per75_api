# Website232 — User Feedback Patch V13

Applied directly from the annotated screenshots supplied with the latest feedback.

## Player Profile
- Removed the remaining lime/green accent treatment from profile labels and controls.
- Centered the player identity under the headshot and aligned the name with the portrait.
- Changed the profile portrait to `object-fit: contain` at full frame size so the player image is not cropped.
- Increased the six-dimension snapshot labels/values.
- Increased the six-dimension radar labels.
- Increased profile table values and percentile text.

## Player Comparison
- Changed Player B's six-dimension percentile bars from blue to the same gold/yellow used by the Player B spider chart.
- Kept Player A bars in the site wine/red.
- Preserved the A red / B gold card treatments.

## Teams
- Forced the site wine/red accent for team-page labels.
- Increased team overview values.
- Increased logo boxes and removed circular/white wrappers.
- Reworked `TeamLogo` so canonical historical logos use the exact TGOlson historical filename convention (`ABBR_YEAR`) first, with canonical Logo_ID/current-logo fallbacks.
- Removed the browser canvas edge-trimming pass that was causing choppy/cut PNG edges.
- Added historical abbreviation fallbacks for defunct/renamed franchises where the canonical team slug is not a modern NBA abbreviation.

## Create Your T75
- Rebuilt the matchup cards around the annotated trading-card reference instead of the previous generic photo-card treatment.
- Cream physical-card body with team-color border.
- Team-color portrait backdrop.
- Team abbreviation watermark where available.
- Full, contained headshot without the previous cover crop.
- Overlapping white name plaque with colored outer border and dark inset line.
- Team-colored position strip below the name plaque when position data exists.
- Five compact stats remain beneath the portrait/name area.
- Preserved the existing matchup/ranking engine and API/data contracts.

## Verification
- `App.jsx` TypeScript transpilation: passed.
- Local API Python syntax check: passed.
- Full Vite build not run because the working project does not have Vite dependencies installed in this environment.
