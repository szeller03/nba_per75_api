# Website160 — Player Profile identity/500 repair

- Fixed the profile route so canonical Player_ID is used for master/profile
  matching whenever available; it no longer falls back to a name that can
  accidentally match multiple records.
- Ambiguous name-only requests no longer silently select one person.
- Normalized identity public-name keys so source-name variants such as
  punctuation/asterisk forms resolve to the same public identity.
- Preserved distinct Player IDs for genuinely different players with the same
  name.
- Added a clean JSON error path for unresolved ambiguous identities instead of
  an unhandled 500.
- The 5-Year Peak `name before initialization` frontend fix from Website159 is
  retained.
