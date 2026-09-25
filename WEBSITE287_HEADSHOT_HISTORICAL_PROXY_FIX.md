# Website287 — Headshot Historical/Proxy Fix

Start: Website286.

## What changed
- Preserved the 4,896-player universe and all statistical/SDI/peak data.
- Kept confirmed/current NBA CDN photos as the primary source.
- For historical candidate records whose latest season is before 2025-26, the API now prefers the Basketball-Reference playing-era photo candidate instead of a post-retirement NBA CDN image.
- Basketball-Reference images are routed through the local API proxy rather than loaded directly by the browser, avoiding the direct remote-image failure visible in the player cards.
- The API proxy tries the bounded Basketball-Reference ID candidate chain.
- Existing alternate Basketball-Reference records (including the 2,860 placeholder replacements and 197 no-URL records) continue to use the alternate source.
- Example explicitly corrected by this logic: Kareem Abdul-Jabbar is no longer forced to use the current NBA CDN retirement-era portrait when a historical B-Ref candidate is available.
- No statistics, eligibility, SDI, peak, comparison, Explorer, Teams, or Create Your Top 75 logic was changed.

## Note
The remaining visual standard is intentionally "playing-era photo first" for historical players. This is a source-selection correction, not a claim that every B-Ref candidate has been visually hand-verified.
