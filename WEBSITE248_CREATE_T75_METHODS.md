# Website248 — Create Your T75 Method Chooser + Direct Player Pool

## Integrated
- Reworked the Create Your T75 landing screen into two equal side-by-side method panels.
- Each method contains a 2x2 grid of T10 / T25 / T50 / T75 cards.
- Added the supplied player artwork as production PNG assets, extracted from the user-provided composite image (no AI player imagery used):
  - Head-to-head: LeBron James, Kevin Garnett, Shai Gilgeous-Alexander, Allen Iverson.
  - Direct selection: Michael Jordan, Wilt Chamberlain, Jerry West, Russell Westbrook.
- Added the direct player-pool builder for every list size.
- Direct builder supports search, selection counts, removal, and up/down ordering.
- Direct selection requires the exact target count before building the list.
- Final lists use whole-row clickable player links to player profiles.
- Added shareable list links using the browser Share API when available, with clipboard fallback.
- Shared list URLs restore the selected/generated list without needing to replay the matchup process.
- Preserved the existing adaptive head-to-head ranking engine and its candidate pools.

## Responsive behavior
- Desktop/tablet: two methods side-by-side; each method is a 2x2 card grid.
- Narrow screens: method panels stack vertically; player-pool builder becomes a single-column pool.

## Validation
- Python asset generation completed successfully.
- App.jsx structure checked with source-level inspection.
- `npm run build` could not be completed because the provided environment's interrupted dependency install left Vite unavailable. No project source dependency changes were made.
