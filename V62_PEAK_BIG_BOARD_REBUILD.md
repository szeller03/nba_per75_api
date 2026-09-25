# V62 — 5-Year Peak Big Board Rebuild

The prior V61 API logs showed the Big Board endpoint was no longer crashing, but the peak implementation still returned zero rows. The peak Big Board has therefore been rebuilt rather than patched.

The Big Board now constructs its peak population directly from the master season dataset:
- Regular season: each season qualifies at >=60% of that season's schedule and >=1,400 MP.
- Regular season peak: five qualifying seasons within a maximum six-calendar-season span; one skipped season is allowed.
- Playoffs: five consecutive qualifying playoff appearances; each >=3 G and >=75 MP; >=35 total games.
- Canonical player identity is applied before deduplicating.
- The selected statistic determines the player's best peak window.
- Percentiles are calculated across the resulting peak population.
- Era filtering is applied to the peak starting season.
- Playoff 5-Year Peak is now handled by the same Big Board function rather than being rejected as regular-season-only.

The API source compiles successfully after the rebuild.
