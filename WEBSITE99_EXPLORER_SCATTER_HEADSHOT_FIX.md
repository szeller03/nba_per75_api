# NBA PER-75 Website99 — Scatter Headshot Reliability Fix

Fixed the scatter headshot rendering path.

- The API route now guarantees every Big Board observation includes the
  canonical `headshot_url` before returning the response.
- This covers regular season, playoffs, career, era-average, and other board
  builders without relying on each builder to remember the field.
- The scatter chart now uses native SVG `<image>` elements with circular
  clipping instead of `foreignObject`, which is substantially more reliable
  for image rendering inside SVG charts.
- A circular border remains around each headshot.
- Fallback circles remain for observations without a valid headshot.
- Hover and click behavior are preserved.

Paired-observation behavior:
The X and Y datasets are independently returned by the Big Board. The chart
then takes their intersection by canonical player + season/scope and removes
rows where either statistic is non-numeric/missing. Therefore the paired
observation count can legitimately change when the selected statistics change.
This is expected and prevents plotting a misleading point where one axis lacks
a valid statistic.
