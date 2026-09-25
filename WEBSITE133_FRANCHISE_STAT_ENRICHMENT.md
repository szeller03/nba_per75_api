# Website133 — Franchise Search Statistic Enrichment

The exhaustive Team Database now enriches every franchise-search row directly
from the Team Analytics team-season dataset.

This fixes the case where a franchise search showed all seasons but every
statistic was `—`.

The enrichment matches:
- normalized franchise identity (including common abbreviations such as OKC)
- season
- season type

The database row remains authoritative for the historical franchise-season
list, while all available analytics values are layered onto it. Missing
statistics remain `—` only when the underlying analytics source truly lacks
that statistic.

The frontend now renders the enriched database rows directly during franchise
search instead of attempting a second client-side join.
