# SDI v4 Profile Root / Identity Fix

Root cause of the "No matching player" regression:
the API preferred an older external NBA_Per75 root and the Website212 package
also lacked the identity registry required by resolve_player_identity().

This build:
- resolves ROOT from the running project's parent directory first;
- includes player_website_identity_v1/website_player_identity_v1.csv;
- includes data/nba_per75_master_v46.csv generated from the supplied current
  player-season source;
- keeps the authoritative SDI v4 season/career/peak artifacts;
- verifies the exact Jokic profile request in-process.

Verified:
Nikola Jokic -> Nikola Jokić
Regular 5-Year Peak -> 2021-22 through 2025-26
SDI v4 -> 88.53137629334783
