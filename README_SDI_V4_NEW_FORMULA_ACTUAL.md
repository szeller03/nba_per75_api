# SDI v4 NEW FORMULA — ACTUAL INTEGRATION

This package supersedes the prior formula-only package. It is wired into the Phase 6 V6 API.

## Regular Season
- Scoring Volume: 22%
- Efficiency: 20%
- Creation / Playmaking: 20%
- Rebounding: 10.5%
- Defense: 22%
- Impact / Value: 5.5%

## Playoffs
Playoff SDI has five categories. Impact / Value is removed because the locked Impact / Value definition is WOWY Net = 100%, and playoff WOWY is unavailable. The former 5.5% is proportionally redistributed:
- Scoring Volume: 23.280423%
- Efficiency: 21.164021%
- Creation / Playmaking: 21.164021%
- Rebounding: 11.111111%
- Defense: 23.280423%

Within playoff Creation, WOWY Offense is removed and the remaining groups are renormalized to 55% Output / 45% Ball Security & Creation Cost. Within playoff Defense, WOWY Defense is removed and the remaining groups are renormalized to 58.333333% Activity / 41.666667% Rate.

## What is actually fixed
The API no longer consumes the legacy playoff SDI CSV for active playoff SDI calculations. It builds the playoff SDI index from the canonical playoff 46-stat percentile layer, and the SDI Big Board uses that active formula layer. Playoff Career and Playoff 5-Year Peak SDI are also derived from the new season-level playoff SDI. Playoff spider/category axes use the five-category formula and no longer return Impact / Value.

The prior package only supplied the formula/config specification; it did not replace the site's active cached/precomputed playoff SDI path. This package fixes that wiring.
