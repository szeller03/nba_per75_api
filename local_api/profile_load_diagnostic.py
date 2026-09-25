import json, time, urllib.request, urllib.parse

BASE="http://127.0.0.1:8000"
PLAYER="P000001"

def get(path):
    t=time.perf_counter()
    with urllib.request.urlopen(BASE+path,timeout=60) as r:
        body=r.read()
        return r.status, time.perf_counter()-t, json.loads(body)

for season_type,season in [
    ("Regular Season","Career"),
    ("Playoffs","Career"),
    ("Playoffs","5-Year Peak"),
]:
    q=urllib.parse.urlencode({
        "season_type":season_type,
        "season":season,
        "percentile_context":"Peak" if season=="5-Year Peak" else "Season",
    })
    try:
        status,elapsed,data=get(f"/api/v1/players/{PLAYER}/profile?{q}")
        print(season_type,season,status,f"{elapsed:.3f}s",
              "percentiles=",len(data.get("percentiles",{})),
              "spider=",bool(data.get("spider") or data.get("peak_spider")))
    except Exception as e:
        print(season_type,season,"ERROR",repr(e))
