# Website288 → Website289 Headshot Presentation Fix

- Retired/historical players now prefer Basketball-Reference imagery even when the registry marks the NBA CDN record verified; current-season players can retain NBA CDN portraits.
- Historical fallback images are normalized server-side to transparent PNGs.
- Background removal uses border-connected near-white flood fill with a wider threshold to catch scanned/printed white backgrounds while preserving internal white uniform details.
- Subject is tightly cropped, then standardized onto a transparent 4:5 canvas with an upward-biased position.
- Player database cards use cover on the normalized transparent canvas so subjects fill the photo area cleanly.
- No statistical or ranking data changed.
