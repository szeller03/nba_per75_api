# NBA PER-75 — Website Design & UX Specification V1

## 1. Design position

NBA PER-75 is a historical NBA analytics site centered on:
- context-aware player percentiles
- PER-75 production
- configurable statistical profiles
- player comparisons
- season-wide Big Boards
- team profiles
- historical exploration

This is a baseline design, not a locked visual specification. Future user-created concepts may override any component without changing the analytical/data contracts.

## 2. Reference principles

### DataBallr-inspired principles
- Section-based top navigation rather than a crowded list of every feature.
- Search-first access to players.
- Dense but configurable statistical tables.
- Deep player pages reached directly from tables/search.
- Tools should feel like distinct research surfaces.

The current DataBallr site uses section navigation and a broad Stats/table experience with sorting, filtering, custom views, comparison, and player deep links.

### Hoopology-inspired principles
- Controls belong directly beside the visualization they control.
- Charts should be genuinely configurable rather than decorative.
- Axis/stat/context selections should update the visualization immediately.
- Highlighting, filtering, comparison, and export should be first-class behaviors.

NBA PER-75 should use these principles without copying either site's visual identity.

## 3. Proposed primary navigation

Top-level navigation:

1. Home
2. Players
3. Big Board
4. Compare
5. Explorer
6. Teams
7. Methodology

Persistent global search:
- Search players
- Search teams
- Jump directly to a player profile
- Search should include all 4,896 canonical players, not only the 2,096 qualified-profile players.

Secondary contextual navigation appears inside major sections rather than expanding the global header.

## 4. Home

Purpose:
Give users an immediate way into the database and communicate what makes PER-75 different.

Hero:
- Large search field: "Search any NBA player..."
- Short explanation of PER-75's contextual percentile system.
- Quick links:
  - Player Profiles
  - Big Board
  - Compare Players
  - Statistical Explorer

Featured modules:
- Featured historical player
- Season Big Board
- Statistical leaders
- Recently explored players (client-side)
- Methodology shortcut

## 5. Player profile

Route:
`/players/{player_slug}`

Header:
- Headshot when verified
- Player name
- Career years
- Teams
- Position
- Profile qualification status
- Share button

If no headshot exists:
- Preserve the same layout.
- Show a neutral blank/placeholder portrait.
- Never hide or downgrade the player because of missing imagery.

Primary controls:
- Season selector
- Percentile context:
  - Season
  - Era
  - Historical
- View:
  - Profile
  - Percentiles
  - Seasons
  - Career

### Profile overview

Six-category profile cards:
- Scoring Volume
- Scoring Efficiency
- Creation & Playmaking
- Rebounding
- Defense
- Impact & Value

Each card:
- category percentile
- compact explanation
- click-through to underlying statistics

### Spider chart

Default:
- Six category axes

Configurable controls:
- Context: Season / Era / Historical
- Axes: six categories or selected statistics
- statistic selection
- percentile display
- normalization mode
- show/hide labels
- compare another player
- compare another season
- reset

The chart is analytical first, decorative second.

### Statistical detail

Organize all 46 statistics by taxonomy:
- Scoring Volume
- Scoring Efficiency
- Creation & Playmaking
- Rebounding
- Defense
- Impact & Value
- Context / Usage / Shot Profile

For each statistic:
- raw value
- percentile
- percentile context
- directionality
- tooltip definition

## 6. Big Board

Route:
`/big-board`

Purpose:
Allow users to view an entire season's percentile population without opening individual profiles.

Core controls:
- Season
- Percentile context
- Statistic
- Category
- Minimum qualification
- Position filter
- Team filter
- Search
- Sort direction

Default table:
- Rank
- Player
- Headshot
- Value
- Percentile
- Team
- Position

Optional modes:
- Single-stat leaderboard
- Category leaderboard
- Six-category profile
- Multi-stat custom table

Player names link directly to profiles.

Headshots are optional display metadata and never determine table inclusion.

## 7. Compare

Route:
`/compare`

Two-panel setup:
- Player A
- Player B
- Independent season selections

Controls:
- Percentile context
- Category selection
- Statistic selection
- Average/weighted aggregation
- Include/exclude categories

Views:
- Spider chart
- Category bars
- Percentile table
- Raw statistic table
- Season-by-season comparison

The comparison API already supports arbitrary season selection and statistic selection.

## 8. Statistical Explorer

Route:
`/explorer`

This is the research/power-user surface.

Core idea:
`Pick statistic → pick season(s) → choose percentile context → inspect population`

Modes:
- Leaderboard
- Distribution
- Scatter
- Historical trend
- Player spotlight

Future extension:
- X/Y statistic scatter
- Select a player to highlight
- Select multiple players
- Compare seasons
- Export/share view

## 9. Teams

Route:
`/teams`

Team index:
- Team
- First season
- Last season
- Number of seasons
- Link to profile

Team profile:
- Team-season selector
- ORtg
- DRtg
- Relative ORtg
- Relative DRtg
- Pace
- historical team comparison

Team comparison:
- Team A / Team B
- independent season selection
- five current team statistics
- directionality-aware comparison

## 10. Methodology

Route:
`/methodology`

Explain:
- PER-75 construction
- qualifying-player population
- 46-stat universe
- Season vs Era vs Historical percentile
- statistic taxonomy
- six-category aggregation
- configurable Dominance Index
- context statistics
- multi-team player-season handling
- missing headshot policy

This should be transparent enough that a user can understand exactly what a percentile means.

## 11. Visual language

Baseline:
- dark-first analytics interface
- restrained accent color
- high information density
- generous spacing around major charts
- strong typography hierarchy
- subtle borders rather than excessive cards
- compact tables
- responsive desktop-first layout with mobile adaptation

Important:
This is intentionally only a baseline. User-provided visual concepts can supersede it.

## 12. Component system

Core reusable components:
- GlobalHeader
- GlobalSearch
- PlayerSearchResult
- PlayerIdentityHeader
- Headshot
- SeasonSelector
- PercentileContextSelector
- StatisticSelector
- CategorySelector
- PlayerSelector
- TeamSelector
- SpiderChart
- CategoryScoreCard
- PercentileTable
- BigBoardTable
- ComparisonTable
- StatisticDefinitionTooltip
- ShareButton
- ExportButton
- EmptyHeadshotPlaceholder
- LoadingSkeleton

## 13. Headshot behavior

States:
- `verified`: render image
- `unavailable`: render blank/neutral placeholder
- no player should be removed because of headshot status

Current coverage:
- 4,896 canonical players
- 4,699 verified headshots
- 197 intentionally blank/unavailable

## 14. Data contracts

The frontend should consume the existing website API contracts rather than reading analytical CSVs directly.

Primary data layers:
- player identity
- player seasons
- player percentiles
- spider statistics
- spider categories
- Big Board
- dominance index
- dominance components
- team index
- team seasons
- team lookup

## 15. URL/state philosophy

Important analytical state should be URL-shareable.

Examples:
`/big-board?season=1995-96&stat=PTS_per75&context=historical`

`/players/michael-jordan?season=1990-91&context=era`

`/compare?a=michael-jordan&a_season=1989-90&b=lebron-james&b_season=2012-13&context=historical`

`/explorer?x=PTS_per75&y=rTS&season=2024-25`

This makes research views reproducible and shareable.

## 16. Accessibility and usability

- Keyboard-accessible controls
- visible focus states
- chart values available in table form
- color should never be the only signal
- tooltips should have text equivalents
- mobile controls should collapse cleanly
- tables should remain usable at narrow widths

## 17. Build order

Phase A — application shell
1. Global navigation
2. Search
3. Routing
4. Design tokens
5. responsive layout

Phase B — player experience
6. Player profile
7. Percentile table
8. Spider chart
9. category cards

Phase C — discovery
10. Big Board
11. Statistical Explorer

Phase D — comparison
12. Player comparison
13. configurable chart controls

Phase E — teams
14. Team index
15. Team profile
16. Team comparison

Phase F — methodology/polish
17. Methodology
18. shareable URLs
19. export
20. loading/error/empty states
21. mobile refinement

## 18. Product principle

The interface should make the database feel exploratory.

The user should be able to start with:
- a player
- a statistic
- a season
- a percentile context
- a comparison
- or a Big Board

and move between those concepts without losing the analytical context.
