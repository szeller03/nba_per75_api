# Website232 User Feedback Patch V8

## Player Profiles
- Increased statistic value typography slightly throughout the profile tables and six-dimension snapshot.
- Increased the six-dimension spider labels for readability and kept the data points on the line endpoints.
- Added a more reliable multi-source headshot loader with retries.
- Added a playing-era headshot override for Kareem Abdul-Jabbar so his profile no longer uses the retired-era NBA CDN portrait.
- The existing canonical headshot registry remains the primary source for other players.

## Big Board
- Percentiles remain underneath the primary statistic value.
- Secondary statistic values now inherit the same Blue → White → Red percentile color scale, using the companion statistic's percentile.

## Player Comparison
- Moved Regular Season / Playoffs and Percentile Context controls onto their own top row.
- Moved each player's season-range selectors onto a dedicated row below.
- Increased comparison headshot size.

## Explorer
- No Explorer layout or chart design changes were made in this patch.

## Teams
- Removed the white circular logo plates from the initial team screening.
- Team logos now prefer the canonical Logo_ID already present in the enriched team master, including Utah Jazz historical logos.
- Increased initial-screening statistic values and success labels slightly while retaining the existing font family.
- Detailed selected-stat values remain the same font family and are now larger/bold rather than using a different type treatment.

## Create Your T75
- Headshots are centered in the card photo frame.
- Added a subtle studio-light radial gradient and inner highlight to replace the flat gray photo background.

## Validation
- `src/App.jsx` transpiled successfully with TypeScript's JSX parser with zero diagnostics.
- `src/api.js` transpiled successfully with zero diagnostics.
- Full Vite build could not be run because this environment does not contain the Vite executable in node_modules.
