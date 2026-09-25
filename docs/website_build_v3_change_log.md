# NBA PER-75 Website V3 — Interactive Player Profile

## Added
- Real six-dimension percentile spider chart.
- Season / Era / Historical context drives spider values.
- Spider values are calculated from the saved 46-stat aggregation specification.
- Category and statistic spider modes are separated so custom axes can be expanded later.
- New API route: `/api/v1/players/{player_id}/spider`.
- No analytical/master data is modified.

## Design policy
The existing visual baseline is unchanged. This build prioritizes functionality so the visual design can be revised later without changing the analytical foundation.

## Next
- Finish arbitrary-stat spider axis selector.
- Add season-wide Big Board.
- Add player-to-player comparison using existing comparison/API contracts.
