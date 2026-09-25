# Website220 — Individual Season Selector Final Fix

Website219 exposed individual seasons in the profile payload, but the UI could
still render only Career and 5-Year Peak when the profile payload shape changed
between views.

Website220 makes the individual-season selector independent of the profile
payload:
- Added `/api/v1/players/{player_id}/seasons?season_type=...`.
- The endpoint uses the same canonical master season source as player profiles.
- PlayerProfile fetches this lightweight season list whenever the player or
  season type changes.
- The selector renders Career + 5-Year Peak + every returned individual season.
- Regular Season and Playoffs use the same canonical season-list mechanism.

Verified directly:
Nikola Jokić Regular Season -> 2015-16 through 2025-26 (11 seasons).
Nikola Jokić Playoffs -> 2015-16 through 2025-26 (11 seasons).
API syntax check passed.
