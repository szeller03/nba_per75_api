# Phase 5C — Player Profile Instant-State Cleanup

Targeted frontend/API request-cache refinement built from the known-good Phase 5A / Phase 4 V4 profile behavior.

## Changes
- Adds player-profile prefetching on hover/pointer-down from Player Search, Players cards, and Big Board navigation.
- Prefetches both Regular Season and Playoffs season bundles before navigation.
- Prefetches both Regular Season and Playoffs 5-Year Peak profile payloads in the background.
- Lets primary profile/bundle requests use the existing shared response cache instead of bypassing it with AbortController signals.
- Adds a short completed-response cache for Playoff profile requests in addition to in-flight deduplication.
- Preserves stale-response protection in PlayerProfile.
- Keeps season rows visible during Regular Season/Playoffs/Peak transitions instead of blanking them first.
- Orders ADVANCED / IMPACT statistics as WOWY Net, WOWY Offense, WOWY Defense, then the remaining advanced statistics.
- No local headshot files are modified.
- No local API data files, SDI calculations, percentiles, or Playoff 5-Year Peak calculation logic are changed.
