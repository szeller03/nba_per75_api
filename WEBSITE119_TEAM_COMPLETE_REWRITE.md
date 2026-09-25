# Website119 — Team Component Complete Rewrite

The prior incremental JSX patches were not sufficient. The supplied Vite log
still showed the old Team component structure at App.jsx:1040.

Website119 replaces the entire Teams() component with a deliberately simple,
valid JSX structure:
- PageShell
  - one team-analytics-page div
    - controls section
    - hero section
    - loading/error state
    - leaderboard section
    - statistic cards section

The summary calculations are moved into a normal meanFor() JavaScript helper,
so there are no inline IIFEs or nested JSX parsing tricks.

This is a component-level rewrite, not another brace/fragment patch.
