from pathlib import Path
import os, sys, json, time, importlib.util

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent
ROOT=Path(os.environ.get("NBA_PER75_ROOT", r"C:\Users\szell\OneDrive\Desktop\NBA_Per75"))

if not ROOT.exists():
    raise RuntimeError(f"NBA_PER75_ROOT does not exist: {ROOT}")

os.environ["NBA_PER75_ROOT"]=str(ROOT)

api_path=HERE/"nba_per75_local_api.py"
spec=importlib.util.spec_from_file_location("nba_per75_local_api", api_path)
api=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=api
spec.loader.exec_module(api)

print("="*88)
print("NBA PER-75 — PLAYOFF 5-YEAR PEAK PRECOMPUTE V2")
print("="*88)
print("Data root:", ROOT)
print("Building once; this may take a while...")

start=time.time()
population=api._playoff_peak_population()
rows=list(population.values())
elapsed=time.time()-start

out=HERE/"cache"/"playoff_peak_v2.json"
out.parent.mkdir(parents=True,exist_ok=True)

payload={
    "version":"playoff_peak_v2",
    "source_root":str(ROOT),
    "created_at":time.strftime("%Y-%m-%d %H:%M:%S"),
    "player_count":len(rows),
    "rules":{
        "single_appearance_min_games":3,
        "single_appearance_min_minutes":75,
        "five_appearance_min_total_games":35,
        "window":"five consecutive playoff appearances",
        "selection":"highest average season-level playoff SDI",
        "percentile_context":"playoff 5-Year Peak population"
    },
    "rows":rows
}

with out.open("w",encoding="utf-8") as f:
    json.dump(payload,f,ensure_ascii=False,separators=(",",":"))

print()
print("PRECOMPUTE COMPLETE")
print("Players with playoff peaks:",len(rows))
print("Cache:",out)
print("Elapsed seconds:",round(elapsed,2))
print()
if not rows:
    raise RuntimeError("ZERO playoff peak profiles were produced. Do not start the server.")
