import json, sys, time
from urllib.request import urlopen
from urllib.parse import quote

BASE="http://127.0.0.1:8000"
PIDS=["P002712","P002997","P003347","P000387","P002950"]

def get(path):
    t=time.perf_counter()
    with urlopen(BASE+path, timeout=30) as r:
        body=r.read()
        status=r.status
    return status, len(body), time.perf_counter()-t

print("Website240 Fix 36 performance test")
print("Make sure nba_per75_local_api.py is already running.")
print()

for pid in PIDS:
    path=f"/api/v1/players/{quote(pid)}/spider?season=Career&context=Career&season_type=Regular+Season"
    try:
        status,size,elapsed=get(path)
        print(f"{pid:8s} spider  {elapsed:.4f}s  HTTP {status}  {size:,} bytes")
    except Exception as e:
        print(f"{pid:8s} ERROR   {e}")

print()
print("A successful Fix 36 test should show each Career spider request staying")
print("roughly in the sub-100ms to low-hundreds-ms range on the local machine,")
print("rather than multi-second request times.")
