"""Website240 Fix 37 public Big Board timing test."""
import json, time, urllib.parse, urllib.request

BASE='http://127.0.0.1:8000/api/v1/public/big-board'
CASES=[
 ('PTS_per75','Historical Percentile','Historical','desc',500),
 ('FGA_per75','Historical Percentile','Historical','desc',500),
 ('FG_pct','Historical Percentile','Historical','desc',500),
 ('rTS','Historical Percentile','Historical','desc',500),
 ('AST_per75','Historical Percentile','Historical','desc',500),
 ('WOWY_Net','Historical Percentile','Historical','desc',500),
]

def run(case):
    stat,season,context,sort,limit=case
    q=urllib.parse.urlencode({'statistic':stat,'season':season,'context':context,'sort':sort,'limit':limit})
    t=time.perf_counter()
    with urllib.request.urlopen(BASE+'?'+q,timeout=30) as r:
        data=json.loads(r.read())
        status=r.status
    return time.perf_counter()-t,status,len(data.get('rows',[])),bool(data.get('public_layer'))

print('Website240 Performance Fix 37 public Big Board test')
print('Make sure nba_per75_local_api.py is already running.')
for case in CASES:
    a=run(case); b=run(case)
    print(f'{case[0]:12s} first {a[0]:.4f}s / repeat {b[0]:.4f}s / HTTP {b[1]} / rows {b[2]} / public={b[3]}')
