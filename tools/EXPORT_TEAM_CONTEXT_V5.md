# Team Competitive Context V5

V3 failed because Land of Basketball returned HTTP 403 for every standings page. V4 then tried Jina, which returned HTTP 401 in the same environment. The pasted run confirms both failures. V5 therefore removes proxy/retry logic entirely and uses **browser-session exports**.

## A. Export Land standings from the browser

1. Open any Land of Basketball page in your normal browser and make sure the site loads normally.
2. Open DevTools → Console.
3. Copy the entire contents of `tools/export_land_standings_bundle.js` into the console and run it.
4. Leave the tab open while it fetches the 75 standings pages. It downloads `land_standings_bundle.json` when finished.

Because the JavaScript runs in the site's own browser origin, it uses the browser session rather than Python's blocked HTTP client.

If the site presents a normal browser challenge, complete it before running the exporter.

## B. Export Basketball-Reference playoff series

Open the all-time Basketball-Reference playoff series-history page in the normal browser and use **Save Page As → Webpage, HTML Only**. Save it as `series.html`.

## C. Build the source layer

From the project root:

```powershell
python local_api/build_team_competitive_context_v5.py --land-bundle "C:\path\to\land_standings_bundle.json" --bref-html "C:\path\to\series.html"
```

The builder then performs **zero network requests**. It parses the two local source exports and writes:

- `local_api/cache/team_competitive_context_v5.json`
- `local_api/cache/team_competitive_context_v5_build_report.json`

## Expected validation

For a complete source bundle:

```text
SEASONS 75
STANDINGS SEASONS 75
SEED ROWS > 0
PLAYOFF FINISH ROWS > 0
```

Do not accept a build with missing standings seasons as authoritative team context.
