# NBA PER-75 Website98 — Headshot Scatter Plot

Scatter plot observations now use the canonical website headshot registry.
- Each point is represented by the player's headshot when a verified URL exists.
- Player ID is checked first, then canonical player name.
- A simple circle remains as a fallback if no headshot exists.
- Hovering enlarges the headshot slightly.
- Clicking the headshot still opens the player's profile.
- Native SVG foreignObject is used, so no new dependency is required.
- The existing Explorer filters and scatter pairing behavior are unchanged.
