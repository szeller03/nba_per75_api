# NBA PER-75 Website V48 — Data Integrity + Era Average

## V48 scope

This build continues from V47 and focuses on the statistical foundations of the Player Profile and Big Board systems.

### Career qualification
- Regular-season career percentile qualification: **G >= 400 AND MP >= 10,000**.
- Playoff career percentile qualification: **G >= 50 AND MP >= 1,500**.
- Raw career statistics remain available even when a player does not qualify for career percentiles.

### Era Average
The Big Board now supports **Scope → Era Average**.

The selected era is aggregated into one player-level observation rather than displaying individual player-seasons.

#### Regular Season Era Average qualification
- **>= 40% participation** across the player's eligible seasons in the selected era.
- **>= 250 games** in the era.
- **>= 6,000 minutes** in the era.

#### Playoff Era Average qualification
- **>= 40% participation** across the player's eligible playoff seasons in the selected era.
- **>= 40 playoff games** in the era.
- **>= 1,250 playoff minutes** in the era.

Participation uses established player-season qualification for the numerator and the player's active span within the selected era for the denominator. The era average itself is calculated from qualifying player-seasons.

### Era-average aggregation
- Per-75 statistics are possession-weighted.
- Additive value statistics such as WS/OWS/DWS/VORP are summed.
- Shooting/ratio statistics use their natural denominator where available.
- Remaining rate/impact statistics are minute-weighted.
- Era percentiles are calculated **only against the qualified player-era population for that same era**.

### Spider stability
Player-profile spider requests now use a request-generation guard so an older asynchronous response cannot overwrite a newer player/season/context selection.

### Statistical Dominance Index
The Statistical Dominance Index remains intentionally deferred for this build. Era Average defaults to PTS_per75 when entered through the UI so the new scope has a working statistical ranking immediately.
