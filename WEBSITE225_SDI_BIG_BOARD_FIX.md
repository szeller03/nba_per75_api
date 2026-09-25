# Website225 — Statistical Dominance Index Big Board Fix

The SDI option was incorrectly routed through the ordinary statistic-percentile
Big Board path. That caused the displayed SDI values to be wrong and sorting to
be inconsistent. Career and Era Average also had no SDI implementation, while
5-Year Peak did not consistently use the authoritative peak source.

Website225 routes the SDI option through the dedicated precomputed SDI v4 data
layer for every scope.

Regular Season:
- Single Season: `data/precomputed_sdi_v4/regular_player_season_sdi_v4.csv`
- Career: `data/precomputed_sdi_v4/regular_career_sdi_v4.csv`
- Era Average: mean of the player's qualifying season-level SDI v4 scores in
  the selected era, using the established Era Average eligibility gates.
- 5-Year Peak: `data/precomputed_5_year_peak/regular_profile_peaks_authoritative_v7.csv`

Playoffs:
- Single Season: `data/precomputed_sdi_v4/playoff_player_season_sdi_v4.csv`
- Career: `data/precomputed_sdi_v4/playoff_career_sdi_v4.csv`
- Era Average: mean of qualifying playoff season-level SDI v4 scores in the
  selected era.
- 5-Year Peak: `data/precomputed_5_year_peak/playoff_profile_peaks_authoritative_v7.csv`

All SDI rankings are sorted by the actual SDI score (higher is better).
Percentiles are calculated against the complete population for the selected
scope before the top-N display limit.

Verified all eight scope/dataset combinations return ranked, descending SDI
values:
- Regular single
- Regular career
- Regular era average
- Regular 5-Year Peak
- Playoff single
- Playoff career
- Playoff era average
- Playoff 5-Year Peak

Jokic checks:
- Regular 2025-26 SDI: 88.264462
- Regular career SDI: 85.512484
- Regular 5-Year Peak SDI: 88.531376
- Playoff career SDI: 79.341808
- Playoff 5-Year Peak SDI: 79.406933
- All tested result sets are correctly ordered by SDI descending.
