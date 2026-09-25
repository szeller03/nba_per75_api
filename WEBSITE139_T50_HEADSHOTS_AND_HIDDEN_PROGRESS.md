# Website139 — T10/T25/T50/T75 UX Fix

## Headshots
The T10/T25/T50/T75 cards now request the site's canonical headshot proxy
endpoint first, using the canonical player ID when available. If the direct
player headshot URL exists, it is used as a fallback if the proxy request
fails.

This avoids relying on potentially stale/invalid direct headshot URLs from
the player-search response.

## Ranking visibility
Removed the live "Current TXX" ranking section entirely.

During the decision process, users only see:
- the current matchup
- decision progress
- the controls needed to continue/reset

The actual ranked T10/T25/T50/T75 is revealed only when the selected decision
budget is reached.
