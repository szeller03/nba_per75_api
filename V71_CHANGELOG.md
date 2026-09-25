# NBA PER-75 Website 71 — Integration Build

Website71 is a new copy of Website70. The Website70 visual system and React/Vite navigation are preserved.

## Added

1. **React/Vite → FastAPI integration**
   - `src/api.js` now uses same-origin `/api/v1` by default.
   - `vite.config.js` proxies `/api/*` to `127.0.0.1:8000`.
   - This removes the need to run a separate static `http.server` frontend and avoids the browser CORS problem caused by `5500 → 8000`.

2. **Player Experience API integration**
   - Player profiles request `/players/{player_id}/categories`.
   - Player profiles request `/players/{player_id}/subcategories`.
   - A compact Player Experience Profile section is rendered when the API returns category data.

3. **Big Board compatibility**
   - The frontend still accepts the original `{rows: [...]}` Big Board response.
   - It also accepts the current FastAPI `{data,total,offset,limit}` precomputed percentile response.
   - The current percentile source is normalized into the existing Big Board row format.
   - Season, era, player search, percentile context, statistic, and sort are applied client-side when using the raw percentile bridge.

## Important limitation of the current FastAPI bridge

The current `/api/v1/big-board` bridge exposes player-season percentile data. It does not yet expose the legacy aggregated SDI/career/5-year-peak Big Board rows through that same response shape. Website71 therefore preserves the old rich-response path when available and displays a note when the raw bridge is being used for an aggregation scope it cannot represent.

This is intentional: the frontend does not invent or recalculate SDI, career aggregation, or 5-year peak values.

## Run

1. Start the FastAPI backend from the NBA_Per75 project root:

```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75"
py -m uvicorn api.player_profile_v1.app:app --reload
```

2. In a second PowerShell window, enter the Website71 directory and install dependencies:

```powershell
cd "C:\Users\szell\OneDrive\Desktop\NBA_Per75\NBA_Per75_Website71"
npm install
npm run dev
```

3. Open the Vite URL shown by npm, normally:

`http://localhost:5173`

No `python -m http.server 5500` is required for Website71.
