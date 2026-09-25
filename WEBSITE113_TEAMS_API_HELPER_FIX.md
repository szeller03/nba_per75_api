# Website113 — Actual Teams Blank-Page Root Cause

The Teams route itself and its import were valid. The crash was inside
`src/api.js`.

`getTeams()` and `getTeamProfile()` had been added using `request(...)`, but
this API module defines `get(...)` and `getWithSignal(...)` — there is no
`request` function.

Therefore clicking Teams executed an undefined function immediately. Because
that exception occurred while the Team effect was starting, React never got
to the page's error state and the route appeared as a blank page.

Website113 changes only these two functions to call the existing `get(...)`
helper, which automatically prefixes `/api/v1`.

Expected calls:
- `/api/v1/teams?...`
- `/api/v1/teams/{team}?...`

No other page/API logic was changed.
