FIX51 — SDI COMPANION PERCENTILE INTEGRATION

Purpose
Add the companion population percentile to the six SDI dimension boxes without changing the underlying SDI raw values or formula.

Display
Each dimension now shows:
  [large raw SDI value]
                 [small] XXth percentile

The companion percentile is a population rank of the raw category SDI score. The raw SDI value remains the primary number.

Method note
The existing Career/5-Year Peak note now starts with a plain-language explanation of SDI raw values and companion percentiles.

Backend
- Regular-season individual SDI companion percentiles are ranked within the same canonical season SDI population used by the canonical regular-season SDI layer.
- Career companion percentiles are ranked across the complete qualified Career population using the current Career raw category SDI scores.
- Existing SDI raw scores, weights, WOWY inputs, and evidence rules are not recalculated by the companion display layer.

Files changed
- local_api/nba_per75_local_api.py
- src/App.jsx
- src/v13_final_corrections.css
