# NBA PER-75 Website — Fix 50.7.6
## Canonical 60/40 Defensive Weighting + Career SDI Integration

This package promotes the validated 60% Blocks / 40% Steals defensive activity weighting to the canonical SDI v4 WOWY calculation path.

### Locked defensive methodology
- Defensive Activity: 35% of Defense
  - STL/75: 40%
  - BLK/75: 60%
- Defensive Activity Rate: 25% of Defense
  - STL%: 40%
  - BLK%: 60%
- WOWY Defense: 40% of Defense

All top-level SDI v4 weights remain unchanged.

### What is included
- Updated career SDI v4 WOWY builder from Fix 50.7.5.
- Updated season SDI v4 WOWY builder to the same 40/60 steal/block split, so career and season SDI do not use conflicting defensive formulas.
- Existing canonical WOWY reconstruction and percentile fixes are preserved.
- Existing Profile Career spider integration continues to read `data/regular_career_sdi_v4_wowy_rts.csv` as the authoritative Career SDI source.
- The builder retains pre-write validation and must be run before the live Career CSV is replaced.

### Recommended run
From the Website241 root:
```powershell
python local_api/build_career_sdi_v4_wowy_v2.py
```

If the seasonal SDI source is rebuilt later, use the existing seasonal SDI builder in `local_api/build_sdi_v4_wowy_v1.py`; it now uses the same 60% block / 40% steal split.

### Expected Gobert Career result
Using the validated current population and inputs, Career Defense should be approximately **78.70**, and overall SDI approximately **67.39**.
