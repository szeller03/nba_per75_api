# NBA PER-75 Website100 — Explorer Career Scope Fix

The Explorer's Career selector was only changing the frontend label/context;
it was still requesting the Big Board with `scope=single`. As a result, the
Explorer continued returning player-season observations rather than one row
per player.

Website100 fixes the API contract:
- `scope=career` now routes to the canonical regular-season career aggregation.
- Each player appears once with their career statistic value.
- Career percentiles use the existing career qualification/percentile logic.
- Career rows expose Career as the season label.
- Career rows include canonical headshot URLs.
- Playoff Career is routed through the existing playoff-career builder.
- Scatter plots use the same career scope, so selecting Career produces one
  paired observation per player when both statistics exist.
- Era behavior and player navigation are preserved.
