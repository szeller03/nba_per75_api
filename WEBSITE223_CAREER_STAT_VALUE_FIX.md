# Website223 — Career Raw Statistic Display Fix

The screenshot exposed a second, distinct issue: percentile values rendered for
Career, but the 46 raw statistic values displayed as dashes.

Root cause:
- Individual seasons already had canonical raw values.
- Career `profile` already contained the correct career aggregates.
- The API's generic `statistic_values` construction was season-oriented and did
  not guarantee that Career display values came from the career profile.
- The frontend also had no profile fallback.

Fix:
1. Career `statistic_values` are now explicitly populated from the canonical
   Career profile for all 46 registry statistics.
2. Individual seasons continue to use the canonical season row.
3. 5-Year Peak behavior is untouched.
4. Frontend lookup order is exact value key -> normalized value key -> profile
   key, preventing a blank value when the payload uses an equivalent key.
5. Profile header uses the canonical individual-season selector list for its
   season count/range.

Verified against Nikola Jokic:
- Career: 46/46 raw values recorded and raw values match the career profile.
- 2024-25: 46/46 raw values.
- 5-Year Peak: 46/46 raw values.
