# Website278 — Create Your Top 75 Pack / Matchup Transition Fix

- Preserved the existing foil basketball-card pack artwork exactly; only changed reveal motion and matchup portrait framing.
- Reworked reveal card animations so every card visibly starts at the center of the pack's top opening, rises vertically, bounces once, then fans outward.
- Extended the pack transition timer so the animation completes before the pack screen unmounts.
- Explicitly seeds the first adaptive matchup immediately after the pack closes, preventing the frozen reveal / “Select a player to continue” state.
- Enlarged and lifted the player portraits on the Create Your Top 75 head-to-head comparison cards so the player fills more of the square.
