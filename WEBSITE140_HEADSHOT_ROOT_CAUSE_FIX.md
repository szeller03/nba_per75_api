# Website140 — T10/T25/T50/T75 Headshot Root-Cause Fix

The previous builds were asking the frontend to load `/api/v1/players/.../headshot`
directly. That endpoint can be useful as a server-side proxy, but the more
reliable source for the T50 cards is the same canonical headshot URL used by
the site's player data.

The root issue was that `api_players()` only returned a headshot when the
canonical identity table itself contained a headshot column. The canonical
headshot registry is a separate source, so many T50 search results had a null
`headshot_url`. The browser then showed an empty image element.

Fix:
- `api_players()` now falls back to `_headshot_url_for(player_id, player_name)`
  from the canonical headshot registry whenever the identity row has no URL.
- T50 cards prefer that returned direct URL.
- If the direct URL fails, the card falls back to the local headshot proxy.
- The API was Python-compile validated before packaging.

This fixes the data path rather than merely changing the image element/CSS.
