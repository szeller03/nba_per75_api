# Website235 — v13 User Feedback Corrections

Built from Website234 / the production Website230 data foundation.

## Player Profiles
- Player cards pass the selected player through router state so the profile can render the real front-card headshot immediately.
- Profile cards lift and flip without requiring a second click on the profile view.
- Profile statistic tables now use a wide horizontal scroll surface so all registered statistics remain available without crushing the values.
- Profile table values are larger and percentage-valued statistics are displayed on a percentage scale.
- Six-Dimension Profile radar is constrained inside its card barrier and displays the six SDI values directly.

## Big Board
- Fixed the undefined season collection that prevented the Big Board from rendering.
- Companion-stat requests now retrieve a sufficiently broad historical population so same player-season context values such as PTS/75 -> rTS can be joined reliably.

## Comparison
- Player headshots use the selected canonical player objects as the first source.
- Percentage statistics are rendered as whole percentages (e.g. 50% rather than 0.5).
- Category tabs use the active category to switch the displayed stat set.
- Comparison radar was reduced and given clearer player-specific visual treatments.

## Explorer
- Restored an explicit Single Season / 5-Year Peak / Era Average / Career view selector while retaining the individual-season selector for Single Season.
- Scatter headshots remain real images with the API endpoint as fallback.

## Teams
- Default overview remains the three-panel greatest-team showcase.
- Filtered/search views condense into one 50-row table.
- Condensed rows include team logos and larger typography.
- Success labels are populated from the existing team master’s regular/playoff team-season records. Playoff records are matched by team and season; playoff W/L is carried into the team analytics cache. Exact round labels are inferred from the existing playoff team-season results rather than inventing a separate data source.

## Create Your T75
- Player-pool tiles use the requested large list number over a player headshot with a gradient treatment.
- Pack-stage preview cards use real player headshots.
- An in-progress localStorage session without a persisted pending matchup is no longer restored into a permanently blank matchup state.
- A recovery effect automatically requests the next pair whenever the engine reaches a valid started state with no pending pair.
- Existing adaptive pairwise ranking logic and candidate pools remain intact.

## Verification
- ZIP archive verified with `unzip -t`.
- Python backend syntax verified with `py_compile`.
- A full Vite production build was not run because npm dependencies are not installed in the execution environment.
