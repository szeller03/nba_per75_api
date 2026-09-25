NBA PER-75 Player Profile — DATA LOCKED PERFORMANCE BASELINE

Performance-only transition optimization build.

- Navigation prefetch is limited to season bundles so click-time requests do not compete with Peak/Playoff profile requests.
- Alternate season/peak contexts are warmed sequentially during browser idle time after the visible profile loads.
- Regular Season and Playoffs bundles are warmed for faster season-type transitions.
- Individual-season spider data is prefetched on season-row hover so row clicks can use the cached response.
- Existing request caching/deduplication remains in place.

Data protection:
- No statistic values, percentile layers, SDI formulas, SDI weights, source routing, or canonical data layers were changed.
- The playoff 5-Year Peak cache adapter only fixes the existing dict/DataFrame interface error and does not alter underlying values or calculations.
