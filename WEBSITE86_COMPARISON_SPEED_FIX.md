# NBA PER-75 Website86 — Comparison Speed Fix

Website85 could appear stuck at "Building weighted comparison…" because the
comparison endpoint searched recursively for the percentile CSV and then
performed repeated player/stat lookups.

Website86:
- Loads the percentile source once into the API cache.
- Uses vectorized player/season percentile lookup.
- Eliminates per-stat repeated CSV discovery.
- Preserves independent Player A and Player B season ranges.
- Preserves percentile context selection.
- Adds `/api/v1/compare-diagnostics` for cache verification.
- Does not alter canonical statistics or weighting methodology.
