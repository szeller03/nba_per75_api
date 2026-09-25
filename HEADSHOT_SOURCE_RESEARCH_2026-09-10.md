# NBA PER-75 — Headshot Source Research / Website292

## What this build actually changes

This build uses the project's existing 4,896-player identity layer and makes the historical-photo source selection explicit for the 3,057 records that were identified as lacking a usable NBA CDN photo (2,860 generic placeholders + 197 records with no NBA CDN URL).

For that population, the site selects the player's Basketball-Reference player-photo URL rather than the NBA generic silhouette. The browser first tries the local API endpoint, so the API can fetch the source image and return the normalized card image. The raw Basketball-Reference JPG is therefore not required to be manually placed into the website's static assets.

## Important source decision

I did not use AI-generated player images or NBA2K/game renders. The fallback source is real player photography already referenced by the project's Basketball-Reference resolution layer.

I also did not repeat the earlier bulk background-removal/canvas-normalization workflow that produced bad crops. Website292 renders the source photograph directly at the UI layer and applies the existing historical treatment rather than rewriting the source pixels.

## Verification status

This is a source-selection build, not a claim that every one of the 3,057 historical records has been independently pixel-verified by a human. The project's prior audit established the 3,057-person problem population; the mapping is deterministic from the project's existing Basketball-Reference candidate layer. The remaining identity-risk population should be visually audited before publication, especially same-name/collision cases.

## External source research

Basketball-Reference maintains an all-NBA/ABA player index and is the project's existing historical-statistics source. Wikimedia Commons has basketball-player and NBA-player categories with file-by-file licensing information, but it is not a comprehensive clean transparent headshot archive. Public NBA-headshot packages/datasets found during research use the NBA CDN and therefore do not solve the historical-era portrait problem.

## Copyright / licensing note

Basketball-Reference player photographs should be treated as externally hosted copyrighted source material unless a separate license permits redistribution. This build hotlinks/fetches them as a fallback instead of packaging a copied photo archive into the ZIP. A final public deployment should confirm the site's rights/terms for the intended use or replace individual images with appropriately licensed/public-domain sources.
