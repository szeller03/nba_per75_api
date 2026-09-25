# V19 — Scope Separation, Season Label Fix, Profile Routing, Playoff Layer

## Big Board
- Added an explicit Scope selector: Single Season vs Career.
- Career is no longer a value in the Season selector.
- Career is no longer a percentile-context option.
- Single Season retains one Historical Percentile · All Seasons scope plus one option per database season.
- Career ignores the single-season percentile context and uses Career percentile methodology.
- Fixed YYYY-YY display conversion so 1999-00 displays as 2000 instead of 1900.
- Big Board rows now use React Router `Link` to the canonical player profile route.

## Player profiles
- Removed Career from the Percentile Context selector.
- Career context is automatic when the Season selector is set to Career; the context control is disabled and displays a status rather than offering a Career filter.
- Added a Regular Season / Playoffs season-type control.

## Playoffs
- Added API/source discovery for a CSV containing playoff/postseason data with player + season fields.
- If a playoff source is present, the profile can display playoff rows for the selected player/season.
- If no playoff source exists, the profile clearly reports that playoff support is present but the data source has not yet been connected.
- No playoff statistics were fabricated or sourced from an unverified dataset.

No regular-season source/master analytical data was modified.
