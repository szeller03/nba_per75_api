# V16 — Big Board Data Source Repair

The V15 Big Board could show only the hard-coded All Seasons option when the
prepared visualization Big Board CSV was not discoverable by its exact filename.

V16 makes the API robust:
1. Try the prepared `big_board_long` CSV.
2. Fall back to any CSV in the visualization folder containing `big_board`.
3. If no prepared Big Board exists, derive the season-wide board from the
   validated player-season percentile foundation.

The API now also recognizes more common raw-value and percentile column names.

The frontend initializes the season selector to `All Seasons · Single-Season`
and retains the returned season list.

No analytical source/master data was modified.
