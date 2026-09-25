# Website142 — Duplicate Matchup Fix

Fixed a race/stale-state bug in the pairwise T10/T25/T50/T75 matchup engine.

## Cause
After a user voted, React state (`comparisons`) was updated asynchronously,
but the next matchup was selected by a delayed callback that could still see
the previous render's comparison history. That meant the just-completed pair
could be selected again.

## Fix
- Added a synchronous `comparisonsRef`.
- The matchup selector now reads the latest comparison history from that ref.
- The ref is updated immediately when a vote is recorded.
- Saved progress restores the ref before matchup generation.
- Start Over and new sessions clear the ref.
- Both the normal pair-selection check and the unasked-pair fallback now use
  the current history.

This prevents the same two players from being presented again in either order
within a ranking session.
