# Team Competitive Context V1

The Teams page now has a dedicated competitive-context source layer instead of inferring postseason success from playoff win totals.

## Sources

- Regular-season seed / conference / postseason qualification: Land of Basketball year-by-year standings pages, following the `YYYY_YYYY_standings.htm` pattern.
- Playoff series / round reached / elimination / champion: Basketball-Reference playoff summary pages, following the `NBA_YYYY.html` pattern.

## Build

Run:

```bash
python local_api/build_team_competitive_context_v1.py
```

The builder discovers the seasons in `data/nba_per75_team_master_enriched.csv`, downloads/caches each source page, parses the standings and playoff series, and writes:

`local_api/cache/team_competitive_context_v1.json`

The local API merges `seed`, `conference`, `playoff_finish`, `playoff_status`, and series information onto team-season analytics rows when the cache exists.

## Important

The existing team analytics `Rk` field is **not** used as the regular-season seed. It is an analytics-table rank and can differ from conference seed.

If a source page cannot be fetched, that season is reported in `team_competitive_context_v1_build_report.json`; the API does not fabricate a seed or playoff round.
