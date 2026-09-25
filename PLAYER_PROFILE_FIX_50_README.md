# Website240 — Player Profile Fix 50

Built from the validated Explorer Fix 49 baseline.

## Scope

This is an isolated Player Profile data-integrity repair. It preserves the existing Profile performance architecture, Explorer Fix 49, Big Board Fix 45, Player Compare Fix 46, SDI v4, WOWY, peak methodology, and canonical headshot system.

### Repairs

- Recomputes regular-season Career percentiles from the authoritative compact Career values instead of trusting stale legacy percentile columns.
- Uses a consistent 0–100 percentile scale with ties handled by average rank.
- Treats TOV/75, TOV%, PF/75, DRtg, and Relative DRtg as lower-is-better for Career percentile calculation.
- Wires the canonical individual-season WOWY Offense, WOWY Defense, and WOWY Net layer into the fast public season-bundle path.
- Preserves WOWY percentile values where the canonical WOWY layer provides them.
- Restores historical 2P% for pre-1979 seasons by deriving it from canonical season payload evidence and calculating its percentile within the existing qualified FGA/75 population. This removes the old dependency on a separate 2P% CSV that was not present in the public indexed path.
- Uses the direct player headshot URL as a safe fallback in the Profile Headshot component, preventing a valid canonical image from being replaced by initials when switching to a context such as 5-Year Peak.
- Changes the Advanced / Impact table order to WOWY Net → WOWY Offense → WOWY Defense.
- Replaces the Career percentile dash with an `NQ` indicator when the player does not meet the Career minimum (400 games and 10,000 minutes), with an explanatory tooltip.

## Important

The generated public SQLite databases are intentionally not replaced by this source-only package. Restart the local API after replacing the files so the compact public layer and Career cache are rebuilt in memory.


REPAIR: Fixed an isolated Profile render regression where seasonCell referenced undefined isCareerRow/careerQualified variables. Career qualification is now derived locally from the Career bundle (400 games and 10,000 minutes).


FIX 50.3 REPAIR
- Corrected lower-is-better percentile direction: TOV/75, TOV%, PF/75, DRtg and Relative DRtg now use the lower-is-better mapping for individual-season and career percentile calculations.
- Corrected playoff percentile direction using the same ranking convention; the smallest value is 100th percentile for lower-is-better stats and the largest is 100th for higher-is-better stats.
- Hydrates 2P% values into the public season bundle whenever the compact payload omits 2P%, using canonical 2P/2PA or FG/3P-derived two-point makes and attempts. This is not limited to pre-1979 seasons.
- Career SDI category cards explicitly display NQ when the career fails the 400 games / 10,000 minutes threshold, using the backend qualification flag when available.
- Context-specific percentile extraction now prefers Season_Percentile for individual playoff/season rows and Career_Percentile for Career rows instead of selecting the first arbitrary percentile field.
