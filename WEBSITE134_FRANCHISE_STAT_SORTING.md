# Website134 — Franchise Search Respects Selected Statistic

Franchise searches remain exhaustive, but they now respect the active Team
Database statistic and order controls.

Examples:
- Search OKC + Relative DRtg + Lowest -> Highest: all OKC seasons, ranked by
  Relative DRtg from lowest to highest.
- Search OKC + NRtg + Highest -> Lowest: all OKC seasons, ranked by NRtg from
  highest to lowest.
- Search OKC + Pace + Highest -> Lowest: all OKC seasons, ranked by Pace.
- A season with no value for the selected statistic remains in the franchise
  database and is placed after seasons with valid values.

The frontend now sends statistic + direction to the exhaustive database API,
so the selected filter is applied server-side rather than merely changing
the displayed column.
