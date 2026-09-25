"""Website240 Fix 38 Big Board cache timing test."""
import time, urllib.parse, urllib.request, json
BASE='http://127.0.0.1:8000/api/v1/public/big-board'
STATS=['PTS_per75','rTS','FTA_per75','AST_TOV','3PA_per75','3P_pct','WOWY_Offense','WOWY_Defense','WOWY_Net']
for stat in STATS:
    q=urllib.parse.urlencode({'season':'Historical Percentile','context':'Historical','statistic':stat,'sort':'desc','limit':500})
    url=BASE+'?'+q
    t=time.perf_counter();
    try:
        with urllib.request.urlopen(url,timeout=30) as r: body=r.read(); status=r.status
        elapsed=time.perf_counter()-t
        payload=json.loads(body)
        print(f'{stat:<16} {elapsed:.4f}s HTTP {status} rows={len(payload.get("rows",[]))} cache={payload.get("cache","legacy")}')
    except Exception as e:
        print(f'{stat:<16} ERROR {e}')
