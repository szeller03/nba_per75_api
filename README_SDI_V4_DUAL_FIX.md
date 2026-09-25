# SDI v4 Dual Fix — Playoff Defense + Career Category Invariance

This build makes the two requested SDI corrections together.

## 1. Playoff SDI: Defense removed

Playoff SDI now has four categories only:
- Scoring Volume — 30.3448275862%
- Scoring Efficiency — 27.5862068966%
- Creation & Playmaking — 27.5862068966%
- Rebounding — 14.4827586207%

These preserve the prior playoff model's relative weights after removing Defense, then renormalize the remaining four categories to 100%.

Impact / Value remains removed because WOWY Net is unavailable in playoffs.
Defense is removed because STL/BLK tracking is historically incomplete and those activity measures are not a sufficiently consistent standalone representation of postseason defense across the full historical sample.

Creation retains its non-WOWY groups at 55% Creation Output / 45% Ball Security & Creation Cost.

The playoff peak-selection SDI path now uses the same four-category formula, preventing canonical playoff peaks from silently using the retired Defense category.
A new cache namespace is used: `playoff_peak_v3_four_category.json`.

## 2. Regular-season Career category scores are invariant

Career six-category spider values remain sourced from the authoritative `regular_career_sdi_v4_wowy_rts.csv` category layer.
The loader now searches the project tree for that exact source so a folder relocation cannot silently trigger a different calculation.

Career category axes are never recomputed from the active season SDI formula as a fallback. If the authoritative career row is unavailable, the axis remains unavailable rather than changing because of a top-level SDI-weight update.

This is specifically intended to prevent a case such as Magic Johnson's Creation / Playmaking category changing solely because the overall SDI top-level weights were changed.

## Frontend

Playoff Player Profile spider labels now show FOUR-DIMENSION PROFILE and render only the four active playoff categories.
Regular-season Career remains a six-category profile.

## Validation

- Python syntax check: PASS
- Config JSON parse: PASS
- Playoff weights sum to 100%: PASS
- Playoff Defense removed from active weight set: PASS
- Frontend four-dimension playoff label: PASS
- Career category fallback isolation: PASS
