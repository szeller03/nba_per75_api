# Website279 — Create Your Top 75 pack center/transition fix

- Reverted the Create-T75-only matchup portrait sizing override introduced in Website278; the comparison/head-to-head card portrait framing returns to the prior design.
- Seed the first head-to-head pair before the pack opens so the UI has a guaranteed valid matchup ready when the pack closes.
- Reworked pack-card reveal motion so every card begins at the exact horizontal center of the pack, rises from the pack opening, bounces once, and only then fans outward.
- Kept the established foil pack artwork untouched.
