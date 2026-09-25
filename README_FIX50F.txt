# FIX 50F — Career WOWY SDI Axis Source Fix

This patch is built from the actual Website242 API/App files supplied by the
user.

Fixes:
- Career Defense now includes the canonical Career WOWY Defense percentile as
  the WOWY Defensive Impact group.
- Sparse STL/BLK career tracking (<50% of career minutes) is excluded before
  the Defense category is formed.
- When sparse tracking is excluded, the remaining Defense group weights are
  renormalized by the existing aggregation engine. For a player such as Wilt,
  this prevents one recorded historical BLK season from creating a 100 Defense
  axis; the canonical Career WOWY Defense evidence can stand on its own.
- Career Impact / Value is now populated from Career WOWY Net, whose group is
  100% of the Impact / Value category.
- Career WOWY Offense/Defense/Net values are reconstructed from the canonical
  season WOWY layer with MP weighting, matching the audited career WOWY method.
- WOWY Career percentiles are calculated separately from raw category SDI.
- Raw category SDI remains the displayed score; the companion percentile is not
  substituted for it.
- UI labels are normalized to:
  Scoring Volume
  Scoring Efficiency
  Creation / Playmaking
  Rebounding
  Defense
  Impact / Value
- Regular-season individual-season SDI handling is left intact.

No change to:
- 22% Scoring / 20% Efficiency / 20% Creation / 10.5% Rebounding /
  22% Defense / 5.5% Impact
- Existing minutes-weighted Career averages
- Separate raw SDI vs companion SDI percentile architecture
