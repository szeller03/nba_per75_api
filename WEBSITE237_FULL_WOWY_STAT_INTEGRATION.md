# Website237 — Full WOWY Statistic Integration

This build promotes WOWY Offense, WOWY Defense, and WOWY Net to first-class individual-player statistics.

## Canonical replacement
- Individual rORtg -> WOWY Offense
- Individual rDRtg -> WOWY Defense
- Individual NRtg -> WOWY Net
- Team rORtg/rDRtg/NRtg remain team-only metrics.

## Integrated surfaces
- Player season data and percentiles
- Player Profile statistic registry
- Big Board statistic source
- Player Comparison statistic universe/categories
- Explorer statistic universe through canonical percentile layer
- Career statistic layer (available-season mean pending denominator-specific career refinement)
- Dynamic regular 5-Year Peak builder via REGULAR_STATS
- SDI v4 WOWY architecture remains separate and authoritative

## Headshots
The frontend now renders only through the local canonical headshot API endpoint. Raw Basketball-Reference URLs are no longer candidates in the React rendering path. The API prefers NBA CDN URLs from the finalized registry, including the preserved Original_NBA_CDN_URL when a fallback registry row exists.
