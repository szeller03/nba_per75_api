# Website262 — Create Your T75 LeBron Art Correction

- Replaced the old LeBron sizing behavior with the user's new transparent cutout.
- Trimmed only the excess transparent canvas surrounding the supplied LeBron artwork; no player pixels were altered or generated.
- This fixes the previous issue where the player looked small because the source PNG was 666x375 while the visible artwork occupied only `(218,14)-(453,375)`.
- LeBron now uses the trimmed artwork at full card-height and is right anchored.
- Iverson was reduced slightly from the previous pass.
- All prior number overflow/clipping fixes remain intact.
