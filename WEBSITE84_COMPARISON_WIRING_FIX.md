# Website84 — Comparison Wiring Fix

Website83 contained the comparison backend and helper but the actual App.jsx
Compare component remained the original placeholder and App.jsx did not import
getPlayerComparison.

Website84 replaces the placeholder with a functional player-search and
comparison UI and explicitly imports the comparison helper.

This is a frontend wiring fix; player profile calculations and source data are
unchanged.
