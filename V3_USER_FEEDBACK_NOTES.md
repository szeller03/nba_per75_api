# Website232 User Feedback Patch V3

Implemented in this build:
- Player profile table display order aligned to the requested Per 75 and Advanced orders.
- Per 75 table includes Games Played immediately after Year.
- Player profile card preserves the canonical/initial headshot when switching to 5-Year Peak.
- Headshot loading retries are more tolerant of a warming local API and preserve fallback behavior.
- Profile backside top section is tightened to reduce excess vertical space.
- Explorer scatter points are centered on their coordinate positions and use the plot-area bounds rather than the full SVG box.
- Teams exact metric values are visually emphasized more strongly than the success label.
- Team logos now use the existing historical team-logo source with season-end-year + historical abbreviation paths.
- Create Your T75 matchup cards use the same contained basketball-card photo treatment and improved card styling.

Pending exact user input:
- The exact set of "basic statistics" previously requested for the Create Your T75 selection cards was not recoverable from the supplied Website232 files or saved project context. The card layout is prepared, but the existing season/career range text is retained until the user supplies the exact statistic list. Do not invent a statistic list.
