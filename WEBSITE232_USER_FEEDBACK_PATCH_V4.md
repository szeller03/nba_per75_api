# Website232 User Feedback Patch V4

Implemented from the September 4, 2026 feedback.

## Player Profiles
- Added explicit source/display aliases for profile table fields:
  - REB/75 -> canonical TRB_per75
  - OREB/75 -> canonical ORB_per75
  - DREB/75 -> canonical DRB_per75
  - rORTG -> canonical Relative_ORtg
  - rDRTG -> canonical Relative_DRtg
- Preserved the requested Per 75 and Advanced table ordering.
- Player headshot loading now retries in the background for a warming local API instead of permanently settling on initials after the first failed load cycle.
- Profile headshot identity is preserved across Career / 5-Year Peak responses.

## Big Board
- Added candidate-pool size selector: T50, T100, T250, T500.
- Default is T500.
- Secondary sorting still operates inside the selected primary-stat candidate pool.

## Explorer
- Scatter bounds are now calculated from the player-seasons actually rendered on the chart instead of the full 10,000-row source universe while only rendering the first 100 rows.
- This prevents a top-PTS/75 chart from being compressed against the far-right edge by low-PTS/75 historical rows that are not displayed.
- X/Y coordinate labels and subtle gridlines remain.

## Teams
- Historical logo rendering now uses the canonical Logo_ID directly against the existing TGOlson/nba-logos source, with the existing local Logo_File path retained as the first available source.
- Team metric values receive stronger visual emphasis; success is intentionally subordinate supporting context.

## Create Your T75
- Matchup cards now use the same collectible-card visual language as the site's Player cards: cream card, framed photo, large player name, and compact stat strip.
- Added the basic card statistics used by the earlier design reference:
  - PTS/75
  - REB/75
  - AST/75
  - STOCKS/75
  - rTS
- STOCKS/75 is calculated as STL/75 + BLK/75 from the canonical profile values.
- Matchup statistics are fetched from the canonical Career profile data for the two players currently being compared.
