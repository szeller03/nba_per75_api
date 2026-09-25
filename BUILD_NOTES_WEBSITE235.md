# NBA PER-75 Website235

## Player Profiles
- AST:TOV now displays to two decimal places.
- NRtg now uses the light blue/light red signed-value treatment.
- rDRtg uses inverse semantic coloring: negative = light blue/good, positive = light red/bad.
- BLK% display no longer treats values such as 0.6 as 60%; it preserves the source percentage-point value.
- 5-Year Peak rows show the peak year span in the Games Played cell (e.g. `09-14`) instead of leaving it blank.
- WS/48 aggregation was corrected so it is MP-weighted (`48 * total WS / total MP`) rather than summed like an additive statistic.

## Big Board
- Secondary statistics remain enabled for the requested companion-stat mappings.
- Secondary statistics are suppressed only for SDI, PF/75, NRtg, PER, BPM, OBPM, DBPM, VORP, WS/48, OWS, and DWS.
- Percentage companions display with percent signs; AST:TOV displays to two decimals.

## Compare
- Spider chart moved back underneath the percentile bars and restored to the larger 520px presentation size.
- Creation & Playmaking now includes AST:TOV and rORtg.
- Defense now includes rDRtg.
- Impact & Value now includes NRtg.
- WS/48 now uses the corrected weighted calculation instead of summing WS/48 values.
- BLK% comparison formatting preserves the source percentage-point value.

## Teams
- Modern team seasons prefer the NBA CDN logo before historical fallback sources, improving reliability for current Suns, Thunder, Celtics and other teams.
- Team analytics cache bumped to v15 so it regenerates from the canonical enriched team-season source, including available Opponent TOV% and Opponent eFG% values.
