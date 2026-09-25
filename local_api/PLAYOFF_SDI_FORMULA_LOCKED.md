# Playoff SDI formula lock

Regular-season SDI is the source of truth and is not modified.

Playoff SDI = regular-season SDI with:
- Defense removed entirely.
- Impact & Value removed entirely.
- WOWY Offense removed from Creation & Playmaking.
- Remaining Creation & Playmaking group weights proportionally renormalized.
- All other statistic weights and group weights inherited unchanged.
- Top-level retained category weights inherited from the active regular-season SDI specification and renormalized only because Defense and Impact & Value are excluded.

Scoring Efficiency therefore remains exactly the regular-season formula, including TS% 25% and rTS 75% within Overall Efficiency, and 2P% 50%, 3P% 40%, FT% 10% within Component Efficiency. FG% is not added.

No frontend/design files are modified by the playoff SDI change.
