# Team Competitive Context V6

V6 removes the confusing `C:\path\to\...` placeholders. The builder automatically finds the two browser exports when they are placed in `local_api\cache\`.

## 1. Browser exports

Create these two files using your normal browser session:

- `local_api\cache\land_standings_bundle.json`
- `local_api\cache\series.html`

The existing `tools\export_land_standings_bundle.js` can be run from the Land of Basketball page to export the standings bundle. Save the Basketball-Reference playoff series-history page as `series.html`.

## 2. Build — no paths required

From the Website232 project root:

```powershell
python local_api\build_team_competitive_context_v6.py
```

Or double-click/run:

```powershell
tools\BUILD_TEAM_CONTEXT_V6.ps1
```

V6 automatically searches the project for the newest matching source files. It makes **zero network requests**.

## 3. Optional explicit paths

If the exports are somewhere else:

```powershell
python local_api\build_team_competitive_context_v6.py --land-bundle "D:\NBA\land_standings_bundle.json" --bref-html "D:\NBA\series.html"
```

## 4. Validation

A complete build must report:

```text
SEASONS 75
STANDINGS SEASONS 75
SEED ROWS > 0
PLAYOFF FINISH ROWS > 0
FAILURES 0
```

If standings are missing or playoff rows are zero, V6 exits nonzero and warns that the cache is not authoritative.
