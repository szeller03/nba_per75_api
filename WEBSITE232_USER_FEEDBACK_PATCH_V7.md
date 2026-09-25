# Website232 User Feedback Patch V7

## Player Profiles
- Career summary and 5-Year Peak summary now use separate API payloads. The Peak view no longer labels the Peak payload as Career, so Career and 5-Year Peak values remain distinct.
- Career percentile rows continue to use the canonical career percentile layer, not single-season percentile rows.
- Games Played is rendered as a whole number.

## Player Comparison
- Fixed the render error caused by `ComparisonSpider` referencing `pa`/`pb` outside the Compare component scope.
- Comparison radar legend now receives and displays the actual player names.

## Teams
- Default overview now independently loads the top Relative ORtg, Relative DRtg, and NRtg populations, so the Relative DRtg overview is the same top-10 population as the dedicated Relative DRtg filter.
- Detailed selected-stat values remain the same font family as the table but are larger and bold.
- Team logos now use the canonical historical abbreviation/year URL pattern plus an official NBA current-logo fallback. Utah Jazz is mapped to UTA / NBA team ID 1610612762.

## Validation
- Python API syntax check passed.
- Static source assertions passed for the requested fixes.
