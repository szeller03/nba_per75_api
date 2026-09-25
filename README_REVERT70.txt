REVERT70 — NBA PER-75 state immediately before FIX70

Purpose:
Restore the pre-FIX70 code state while retaining the isolated FIX69 regular-season SDI locked-weight cache correction.

Restored code:
- src/App.jsx from FIX68
- local_api/nba_per75_local_api.py from FIX68

Retained data correction:
- local_api/cache/regular_sdi_v4_wowy_player_seasons.csv from FIX69

NOT included:
- FIX70 Player Profile performance changes
- public_data_layer.py from FIX70
- any changes to SDI formulas beyond FIX69

This package is intentionally conservative. Do not use it as a replacement for the user's full Website242 data directory; copy only these files into the corresponding locations of the current Website242 project.
