# NBA PER-75 Website78

## Purpose
Fix profile loading/state synchronization without changing the underlying
NBA statistics or playoff peak calculations.

## Changes
- Added abortable, generation-aware profile requests.
- Added profile-context cache keyed by player + season type + season +
  percentile context.
- Prevents stale Career/Playoffs/5-Year Peak requests from overwriting the
  currently selected profile.
- Adds a unified loading state instead of rendering missing values while the
  selected context is still loading.
- Adds a bundle API helper for atomic profile retrieval.
- Keeps the existing Website77 playoff peak cache and percentile repair.
- Does not recalculate SDI or playoff peaks.

## Intended result
When a player is selected, Career should populate on the first render.
Changing Playoffs/Regular Season or Career/Single Season/5-Year Peak should
cancel obsolete requests and render only the current selection. Returning to
Career should use the cached profile bundle immediately.
