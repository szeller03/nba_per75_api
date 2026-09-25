# Regular 5-Year Peak v6 Runtime Contract

The Regular Season Player Profile 5-Year Peak endpoint MUST read:

`data/precomputed_5_year_peak/regular_profile_peaks_authoritative_v6.json`

It must not use:
- regular_profile_peaks.json
- any legacy regular peak cache
- `_canonical_five_year_peak_profile` request-time reconstruction

Cache key: `__precomputed_regular_peak_profiles_v6_authoritative__`

Jokic authority check:
Nikola Jokić -> 2021-22, 2022-23, 2023-24, 2024-25, 2025-26
(start year 2022, end year 2026).
