FIX60 — Playoff 5-Year Peak SDI display fix

Based on FIX59. Narrow display plumbing fix only. The canonical playoff peak population uses `seasons`, while the helper was reading only the legacy `peak_seasons` key, causing zero selected years and blank category axes. FIX60 supports both keys and initializes the axes safely. No formulas, weights, headshots, or underlying data values changed.
