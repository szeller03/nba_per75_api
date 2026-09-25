# NBA PER-75 Website218 — Profile Data Repair

This build is based on Website217 and preserves the working canonical regular
5-Year Peak/SDI v4 system.

## Restored project data contracts
- data/statistic_registry_v3.csv — canonical 46-stat registry
- player_profiles_v1/player_season_profiles.csv — canonical season profile source
- player_data_v1_1/player_seasons_v1_1.csv — 46-stat season layer
- player_analytics_v1_2_dreb/historical_percentiles_v2_1/ — 46-stat long + wide
  percentile sources with Season, Era, and Historical percentiles
- player_headshots_final_v1/ — supplied 4,896-player headshot registry
- player_website_identity_v1/ — canonical website identity/headshot integration

## Exact repairs
1. Season labels in the percentile source now match the UI's YYYY-YY format.
2. Every canonical profile season returns all 46 registered statistics.
3. DREB_pct is restored from the project's established DRB% -> decimal source
   relationship where the source contains DRB%.
4. Exact ratio-derived statistics are filled only when their source totals support
   the calculation (FG%, 2P%, 3P%, FT%, TS%, FTr, 3PAr, AST/TOV, NRtg and
   relative ratings).
5. The frontend's /categories and /subcategories requests now have API routes.
6. The Wikimedia/random headshot fallback has been completely removed. Headshots
   come only from the supplied canonical registry URLs.
7. The existing SDI v4 / regular 5-Year Peak cache is preserved.

## Verification
- Big Board startup cache: existing Website217 cache retained.
- Playoff 5-Year Peak cache: existing working cache retained.
- Jokic regular 2024-25 profile: 46/46 percentile rows.
- Jokic Career profile: 46/46 percentile rows.
- Jokic regular 5-Year Peak: 2021-22 through 2025-26; SDI v4 88.53137629334783.
- Jokic season/career/peak spider: all six dimensions returned.
- Jokic headshot URL: canonical NBA CDN URL from supplied registry.
- API syntax/import: passed.

## Important source-data boundary
Some source-defined Basketball-Reference advanced statistics remain null in the
current master for certain player-season rows, especially aggregate traded-player
rows (2TM/3TM/etc.). Website218 does NOT fabricate PER/BPM/WS/VORP/etc. for those
rows. A missingness audit is included at:
data/PROFILE_STAT_MISSINGNESS_AUDIT_V1.csv

Those values require the existing project advanced-stat source/cache to be applied
to the affected player-season identities. This build intentionally does not replace
that source with a new external dataset.
