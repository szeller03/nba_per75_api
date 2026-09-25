# Regular 5-Year Peak — Authoritative Cache

The Player Profile regular-season 5-Year Peak is now served exclusively from:

`data/precomputed_5_year_peak/regular_profile_peaks.json`

The cache was generated from the supplied player-season dataset using the
revised SDI v4 top-level weights:

- Scoring Volume 20.0%
- Scoring Efficiency 18.0%
- Creation / Playmaking 18.0%
- Rebounding 10.5%
- Defense 20.0%
- Impact / Value 13.5%

The live/legacy request-time regular peak selector is not used when the
precomputed record exists.
