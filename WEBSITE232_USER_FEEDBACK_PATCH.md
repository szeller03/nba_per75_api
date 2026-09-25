# Website232 — User Feedback Patch

Implemented in the existing Website232 frontend:

- Player 5-Year Peak headshot now preserves the canonical player identity/headshot from the initial player result when the peak payload omits it.
- Individual player seasons are clickable. The selected season is highlighted and its six-dimension spider values replace the career/peak spider values.
- Player profile mini spider now uses explicit grid polygons, axes, connecting line, and visible points instead of the previous filled/glob appearance.
- Player profile and Big Board percentile displays are rounded to whole percentages.
- Big Board adds a secondary Highest/Lowest filter that sorts only within the already-loaded primary-stat candidate pool (the primary top-100 pool is preserved).
- Big Board rank/player/season typography is matched to the primary stat value size.
- Player comparison spider is larger, has visible points, and uses a fixed 0–100 percentile scale so neither player's value defines the maximum.
- Explorer distribution restores a bar-chart visualization above the existing table.
- Explorer scatter now shows subtle coordinate gridlines and X/Y tick values.
- The original Website232 Teams page/analytics UI is restored at `/teams`; the newly staged TeamPages UI is no longer used to replace the established Teams experience.
- Team Comparison remains available separately at `/compare/teams`.

Important: the Magic Johnson-style percentile calculation issue is not silently replaced with a new frontend formula. Website232 does not contain the authoritative percentile calculation source/API implementation needed to verify and repair that underlying value. The frontend now displays whatever canonical percentile the API supplies, rounded to a whole number. The authoritative percentile source should be repaired at the API/data layer rather than creating a competing client-side percentile source.
