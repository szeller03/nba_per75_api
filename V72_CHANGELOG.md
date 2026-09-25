# NBA PER-75 Website72

Website72 is based on Website71.

## Purpose
This version prepares the React/Vite frontend for the canonical 5-Year Peak
profile data exposed by the NBA PER-75 API, including playoff peaks.

## Important
This frontend does NOT recalculate SDI or peak percentiles. Those values must
come from the canonical v5 backend peak bridge/JSON profiles.

## Peak fields supported
- peak_start_year
- peak_end_year
- peak_seasons
- skipped_seasons
- peak_sdi
- sdi_percentile
- peak_statistics_json

The API remains the source of truth.
