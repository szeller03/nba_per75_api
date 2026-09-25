Website240 Explorer Fix 47

BASELINE
- Built from the current Website240 source uploaded for the Explorer phase.
- Preserves Player Profiles, Player Compare, Big Board, SDI v4, WOWY, and headshot architecture.

EXPLORER CHANGES
1. Population controls: T25 / T50 / T100 / ALL.
   - T100 is the default.
   - ALL means every qualifying player-season remaining after the selected filters/ranges; it is NOT T1000.
   - T25/T50/T100 are ranked from the common X/Y population using the mean of the two statistics' historical percentiles.
2. Numeric statistic ranges for both X and Y axes.
   - Blank min/max means the full available range.
   - Ranges are applied before the T25/T50/T100 cap.
   - Bounds shown as placeholders come from the full common population.
3. Explorer algorithm fix.
   - Old behavior: independently fetched top 1,000 X and top 1,000 Y Big Board rows, then joined them.
   - New behavior: creates one common player-season population where both statistics exist and both statistic-specific qualification gates pass, then applies ranges and population size.
4. One compact public Explorer request replaces the two independent Big Board scatter requests for regular-season single-season Explorer.
5. Career / 5-Year Peak / Era / Playoff Explorer views use a complete-population legacy fallback rather than the old 1,000-row axis truncation.
6. Existing chart switching, search, season/era/scope controls, player click-through, and distribution panel are preserved.

FILES CHANGED
- src/App.jsx
- src/api.js
- src/styles.css
- local_api/public_data_layer.py
- local_api/nba_per75_local_api.py

INSTALL
Replace the corresponding files in your current Website240 project with the files in this package. Do not replace your existing data/public databases with this package; this source bundle intentionally omits generated databases and caches.
