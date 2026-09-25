# Team Competitive Context V8

V8 removes the manual JSON/HTML bundle requirement. It uses an installed Chrome or Edge browser to fetch the public source pages and saves the HTML automatically in `local_api/cache/team_competitive_context_v8_sources/`.

From the website root run:

```powershell
python local_api/build_team_competitive_context_v8.py
```

If Chrome/Edge is not auto-detected:

```powershell
python local_api/build_team_competitive_context_v8.py --browser "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

For a visible browser window (useful if a source presents an interstitial):

```powershell
python local_api/build_team_competitive_context_v8.py --visible
```

The builder needs no `land_standings_bundle.json`, no `series.html` supplied by the user, no Jina, and no Python HTTP requests.

It will stop with a nonzero exit code if all 75 standings seasons are not parsed or no playoff series are parsed. Do not use an incomplete cache as authoritative.
