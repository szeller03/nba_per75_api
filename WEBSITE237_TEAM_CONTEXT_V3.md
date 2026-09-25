# Website237 — Team Competitive Context Builder V3

This version separates the two external competitive-context sources and prevents Basketball-Reference rate limiting from blocking the historical build.

## Sources

- Land of Basketball: regular-season conference standings, seed, W/L, and postseason qualification.
- Basketball-Reference: NBA/ABA playoff series history; the builder filters to NBA series and derives the highest round reached, champion, and Finals appearance.

## Recommended B-Ref workflow

Basketball-Reference may return HTTP 429 to automated requests. Do not repeatedly retry it. Save the `playoffs/series.html` page locally using a normal browser, then run:

```bash
python local_api/build_team_competitive_context_v3.py --bref-html "C:\\path\\to\\series.html"
```

The default local cache location is:

```text
local_api/cache/team_competitive_sources_v3/bref_playoff_series_history.html
```

Once that file exists, reruns use it without making another B-Ref request.

## Standings-only test

```bash
python local_api/build_team_competitive_context_v3.py --skip-bref
```

## Output

```text
local_api/cache/team_competitive_context_v3.json
local_api/cache/team_competitive_context_v3_build_report.json
```

The builder never treats an unavailable external source as a valid value. Missing seed or playoff finish is reported rather than guessed.
