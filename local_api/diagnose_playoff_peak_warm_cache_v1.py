import json,time,urllib.request,urllib.parse
BASE="http://127.0.0.1:8000"; PLAYER="P000001"
q=urllib.parse.urlencode({"season_type":"Playoffs","season":"5-Year Peak","percentile_context":"Peak"})
url=f"{BASE}/api/v1/players/{PLAYER}/profile?{q}"
for n in (1,2):
    t=time.perf_counter()
    with urllib.request.urlopen(url,timeout=10) as r:
        body=r.read(); status=r.status
    elapsed=time.perf_counter()-t
    d=json.loads(body)
    print(f"REQUEST {n}: STATUS={status} SECONDS={elapsed:.3f} PERCENTILES={len(d.get('percentiles',{}))} SPIDER={bool(d.get('spider') or d.get('peak_spider'))}")
