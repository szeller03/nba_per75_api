# NBA PER-75 Website 71

Website70 is preserved as the design/navigation baseline. Website71 adds the
API integration without replacing the React/Vite architecture.

## What changed

- React/Vite remains the frontend; npm is still the frontend runtime.
- Vite proxies `/api/*` to `http://127.0.0.1:8000`, avoiding browser CORS for local development.
- `src/api.js` now defaults to same-origin `/api/v1` and supports the player experience category/subcategory endpoints.
- Player profiles now surface the connected Player Experience category data when available.
- The Big Board accepts both the older rich `{rows: ...}` API response and the current FastAPI precomputed percentile `{data,total,...}` response.
- The current FastAPI percentile source is normalized client-side for player-season ranking by the selected statistic/context.
- Existing routes, styling, and navigation are retained.

## Run

From this website directory:

```powershell
npm install
npm run dev
```

The frontend runs on Vite at `http://localhost:5173` and proxies API calls to
`http://127.0.0.1:8000`.

The FastAPI service must be running separately:

```powershell
py -m uvicorn api.player_profile_v1.app:app --reload
```
