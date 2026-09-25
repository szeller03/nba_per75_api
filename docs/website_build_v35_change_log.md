# V35 — Playoff 46-Statistic Expansion

The regular-season project has a canonical 46-stat registry. The playoff
percentile layer previously exposed only 22 statistics.

V35 creates a playoff 46-stat contract with explicit availability.

Supported from the current B-Ref totals / possession data include the 17
Per-75 counting/rate statistics, four shooting percentages, TS%, FTr, 3PAr,
USG%, and TOV%.

Metrics requiring unavailable opponent/team advanced inputs or separate
advanced-stat sources remain missing:
rTS, ORtg, DRtg, Relative ORtg/DRtg, PER, BPM, OBPM, DBPM, VORP, WS, OWS,
DWS, WS/48, and opponent-dependent rebound/assist/steal/block percentage
metrics.

No unsupported statistic is fabricated.

The registry still contains all 46 statistics, so the website's 46-stat
customization architecture remains intact.
