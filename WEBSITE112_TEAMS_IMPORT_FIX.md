# Website112 — Teams Blank Page Import Fix

Root cause identified in Website111:

The Teams component correctly called `getTeams()` and `getTeamProfile()`, and
`src/api.js` exports both functions, but `src/App.jsx` did NOT import either
function.

Because the functions are referenced when the `/teams` route mounts, the
browser throws a runtime ReferenceError and React renders a blank page.

Website112 adds both functions to the existing API import. No Team logic,
Player Profiles, Explorer, Compare, Big Board, or API data behavior is
changed.
