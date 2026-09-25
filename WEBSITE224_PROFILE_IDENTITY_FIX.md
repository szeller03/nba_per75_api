# Website224 — Profile Identity Resolution Fix

The 222/223 profile API could return HTTP 500 for a valid player when the URL
used a public/source ID such as P003562.

Root cause:
`_profile_data_identity()` normalized names differently in scalar Python and
pandas code. The pandas regex was case-sensitive and stripped uppercase
characters before comparison, so `Nikola Jokić` became `ikola oki` and could
not match the canonical master-season name.

Fix:
- Normalize to casefold before removing non-alphanumeric characters in both
  scalar and pandas identity paths.
- A valid public/source player ID is now mapped to the canonical master
  Player_ID used by season/profile data.
- Career profile construction is defensive and cannot call `.keys()` on a
  missing career profile.

Verified:
- P003562 -> public identity Nikola Jokić -> canonical data ID nikola-joki.
- Jokic Career: 46/46 raw statistics.
- Jokic 2024-25: 46/46 raw statistics.
- Jokic 5-Year Peak: 46/46 raw statistics.
- Python API syntax/import passes.
