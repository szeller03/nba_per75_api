# NBA PER-75 Website77

Fixes the Website76 cache-path problem.

Website76 assumed `playoff_peak_v2.json` had already been copied into the
new website folder. Website77 automatically searches the previous Website74
and Website73 folders (plus the NBA_Per75 API cache locations) for the
existing playoff peak cache and copies it into Website77 before repairing
percentiles.

If no prior cache exists, it stops safely and tells you to run the bundled
27-second peak builder.

No peak calculation rules were changed.
