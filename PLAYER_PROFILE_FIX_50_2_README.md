# NBA PER-75 — Player Profile Fix 50.2

## Purpose
Targeted repair for the Player Profile data issues reported after Fix 50.1.

## Changes
- Corrected the shared playoff percentile engine so higher-is-better statistics rank upward to 100 and lower-is-better statistics rank upward to 100 at the low end. This repairs playoff season/career percentile direction and also fixes downstream consumers that reuse the engine.
- Corrected the playoff long-percentile builder's local percentile implementation with the same direction-aware definition.
- Corrected the regular Career percentile warm-up path because it reuses the shared percentile engine for career SDI/profile data.
- Corrected the standalone career-percentile builder to honor lower-is-better statistics.
- Added a historical 2P% value hydration fallback. When a regular-season profile row has 2P/2PA (or can derive them from FG/FGA and 3P/3PA) but no persisted 2P_pct field, the Profile now displays the derived 2P% instead of a blank. This is a value-display repair and does not overwrite source data.
- Added the same 2P% hydration fallback to playoff profile values when necessary.
- Career six-dimension SDI categories now display `NQ` when the Career profile does not meet the Career qualification gate of G >= 400 and MP >= 10,000, instead of showing misleading category numbers.

## Preserved
- Fix 49 Explorer architecture and layout/data fixes.
- Fix 46 Player Compare performance work.
- Fix 45 Big Board architecture.
- Fix 42 Profile performance lock.
- SDI v4 weights and WOWY data layer.
- 5-Year Peak methodology and caches.
- Canonical headshot system.

## Validation
- Python syntax check passed for `local_api/nba_per75_local_api.py`.
- JavaScript syntax check passed for `src/api.js`.
- JSX source was checked through static source assertions; Node's direct syntax checker does not accept `.jsx` as an input extension.
- ZIP integrity verified after packaging.
