# V63 — Player Profile 5-Year Peak Repair

The Big Board 5-Year Peak engine is working in V62. V63 focuses only on the Player Profile peak presentation/API contract.

Fixes:
- Player Profile peak statistic rows now explicitly map each statistic name to `data.statistic_values`, so the raw five-year value is displayed rather than `—`.
- Peak percentile rendering accepts `Peak_Percentile` and fallback percentile field names.
- The API now returns both `Value` and explicit `Peak_Value` for each peak statistic.
- The existing canonical SDI-selected five-season window remains unchanged.
- The peak spider continues to consume `Peak_Percentile` from the canonical peak profile.

No scrape/master data is changed.
