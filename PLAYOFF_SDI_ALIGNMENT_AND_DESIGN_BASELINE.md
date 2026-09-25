# Playoff SDI Alignment + Frontend Design Baseline

Base:
- Local API supplied by the user
- Frontend `src/` supplied by the user

Protected:
- Regular-season SDI constants and formula are unchanged.
- Existing canonical playoff statistic/percentile routing is unchanged.
- User-supplied `src/App.jsx` and all supplied frontend CSS/JS are preserved byte-for-byte.

Playoff-only change:
1. Retain Scoring Volume, Scoring Efficiency, Creation & Playmaking, Rebounding.
2. Exclude Defense and Impact & Value.
3. Start from the active regular-season aggregation specification.
4. Scoring Efficiency therefore inherits the regular-season specification (including
   Overall Efficiency 60% with TS% 25% / rTS 75%, and Component Efficiency 40%
   with 2P% 50% / 3P% 40% / FT% 10%).
5. Creation & Playmaking removes only the unavailable playoff WOWY Offense group;
   the remaining regular-season Creation groups are proportionally renormalized.
6. The four retained playoff top-level category weights are derived from the
   active regular-season top-level weights and renormalized to 100%.

Important:
The supplied API package does not include the canonical raw playoff percentile CSV,
so the old `local_api/cache/playoff_sdi_v4_player_seasons.csv` cannot be truthfully
recomputed inside this package. The runtime authoritative playoff index now builds
from the canonical playoff percentile layer when that source is available, and
`local_api/rebuild_playoff_sdi_v4.py` rebuilds the cache without changing regular SDI.

The supplied frontend `src/App.jsx` SHA-256 is:
7b74c65240e31bc1aa7f96f7d5def79f53ac573d0d847f7ab14c616b487675a3
