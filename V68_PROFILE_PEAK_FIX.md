# V68 — Player Profile 5-Year Peak Async/Loading Fix

The supplied API log showed the 5-Year Peak profile request itself returned HTTP
200, followed by a long delay and then expensive Career spider/context requests.
Those auxiliary requests were unrelated to the precomputed peak data.

V68:
- Caches `regular_profile_peaks.json` in the API after its first read.
- When season = `5-Year Peak`, the frontend does NOT request the normal
  season/career Spider Chart endpoint.
- When season = `5-Year Peak`, the frontend does NOT request the normal Context
  endpoint.
- The All-46-Stats spider request is also skipped for the precomputed peak view.
- Peak statistics and percentiles are rendered from the precomputed profile
  record directly.

This leaves the existing Big Board untouched.
