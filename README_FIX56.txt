FIX56 — Career Creation Profile Plumbing Fix

Fixes the response-ready regular-season Career Profile cache so the Creation / Playmaking axis is sourced from the corrected canonical season SDI cache packaged with this patch.

Locked Creation formula represented by the canonical season layer:
- Creation Output: 38.5% (AST/75 80%, AST% 20%)
- Ball Security / Creation Cost: 31.5% (AST:TOV 100%)
- WOWY Offensive Impact: 30% (WOWY Offense 100%)

The Career Creation score is MP-weighted from canonical season Creation SDI and ranked against the same qualified Career population. This fixes the stale-cache path that could make Magic Johnson and Michael Jordan render the same rounded Profile percentile.

Profile continues to display percentile only. Raw SDI remains in the data/Big Board layer.

No headshots were changed.
No other SDI category formulas were changed.
