NBA PER-75 — Create Your T75 v5

Scope: SRC + Local API

Restored locked sections:
- Teams presentation/component restored to the locked Teams source baseline.
- Local API restored to the locked v124 backend, including the verified team four-factors overlay and relative TOV fix.
- Explorer backend restored to the locked Explorer/v124 public-data layer, including WOWY and playoff Explorer support.
- Explorer/Teams CSS restored from the latest locked source baseline.

Create Your T75 fixes:
- Fixed the matchup-card initialization race: the randomized candidate pool is now built from the selected T10/T25/T50/T75 key before React applies the new mode state.
- This prevents an empty candidate pool and restores the two player cards immediately after selecting a head-to-head mode.
- Kept the v4 Jokic identity/stat loading fallbacks.
- Kept the v4 bounded adaptive insertion-ranking algorithm.
- Kept the v4 compile fix for the duplicate getPlayerSeasonBundles import.

Protected sections not intentionally changed:
- Player Profiles
- Big Board
- Teams data/calculations beyond the locked v124 API
- Explorer data/calculations beyond the locked v124 API
