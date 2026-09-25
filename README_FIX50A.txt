# FIX 50A — SDI Canonicalization

This targeted patch is for the current NBA PER-75 SDI work.

## Locked raw SDI formula

Regular-season top-level weights:
- Scoring: 22%
- Efficiency: 20%
- Creation / Playmaking: 20%
- Rebounding: 10.5%
- Defense: 22%
- Impact / Value: 5.5%

Raw SDI is calculated first. Companion SDI percentiles are calculated afterward and
do not feed back into raw SDI.

## What this patch changes

1. Career SDI builder uses the current 22/20/20/10.5/22/5.5 weights.
2. Career SDI builder loads the supplied authoritative subcategory CSV rather than
   an older hard-coded formula.
3. Career evidence gating excludes historically sparse tracking inputs when their
   observed career minutes are below 50%; unavailable evidence is omitted and
   remaining weights are renormalized.
4. Companion SDI/category percentile direction is corrected so higher raw score
   = higher percentile.
5. Adds a read-only audit script.

## Important

This patch does NOT redesign the site or alter the established minutes-weighted
Career aggregation layer. It is a targeted data-layer repair for Fix 50A.

Before deploying, make a backup of the current data/cache. Then rebuild the
canonical Career SDI layer and run the companion-percentile pass.
