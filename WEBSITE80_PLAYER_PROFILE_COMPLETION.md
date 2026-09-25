# NBA PER-75 Website80 — Player Profile Completion

This version focuses on completing and stabilizing the player profile experience
without changing the canonical data calculations.

## Changes
- Career is the immediate default profile view.
- The profile no longer first requests an unspecified/latest season and then
  changes to another season.
- Profile + spider + context data are loaded as one selected-context operation.
- Abortable requests prevent stale selections from overwriting the current view.
- Completed profile contexts are cached in the browser.
- Player experience category/subcategory requests are cached per player.
- Playoff 5-Year Peak continues using the precomputed peak spider payload.
- Custom-stat spider remains separately requestable.
- A unified loading state is shown while the selected context is loading,
  avoiding temporary `—`/`Percentile N/A` states that looked like missing data.
- No SDI, percentile, peak-window, or statistical calculations were changed.

## Scope
This is a profile-experience completion pass. Big Board, comparison, and
leaderboards are not redesigned in this version.
