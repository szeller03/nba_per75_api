# Website132 — Franchise Search Values

Fixed the franchise-search path so it no longer drops team-seasons just because
the selected statistic is unavailable.

When searching a franchise:
- Every database team-season remains visible.
- Available selected-statistic values are displayed.
- Missing historical values display `—`.
- The rows are still chronologically represented by the exhaustive Team
  Database.
- The analytics row is merged with the database row so the UI gets both the
  complete franchise record and its available statistical values.
