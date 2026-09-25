# V36 — Playoff 46-Stat Source-Column Fix

V35 failed because its registry requested `PTS_per75` while the existing V2
playoff statistical output uses `PTS_Per75` (capital P).

The same correction is applied to all Per-75 source fields.

A case-insensitive resolver was also added so equivalent source-column casing
does not cause another build failure.

The 46-stat registry and unsupported-statistic policy are unchanged.
