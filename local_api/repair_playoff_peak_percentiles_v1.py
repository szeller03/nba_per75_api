from pathlib import Path
import json, math, time, shutil

ROOT=Path(__file__).resolve().parent
CACHE=ROOT/"cache"/"playoff_peak_v2.json"

LOWER={"TOV_per75","PF_per75","TOV_pct","DRtg","Relative_DRtg"}

def pct(vals,target,lower=False):
    vals=sorted(vals, reverse=not lower)
    if not vals: return None
    # Percentile convention used by the API: best = 100, worst = 0.
    n=len(vals)
    rank=sum(v <= target for v in vals) if not lower else sum(v >= target for v in vals)
    return 100.0*rank/n

def main():
    if not CACHE.exists():
        candidates = [
            Path(r"C:\\Users\\szell\\OneDrive\\Desktop\\NBA_Per75_Website74\\local_api\\cache\\playoff_peak_v2.json"),
            Path(r"C:\\Users\\szell\\OneDrive\\Desktop\\NBA_Per75_Website73\\local_api\\cache\\playoff_peak_v2.json"),
            Path(r"C:\\Users\\szell\\OneDrive\\Desktop\\NBA_Per75\\api\\player_profile_v1\\cache\\playoff_peak_v2.json"),
            Path(r"C:\\Users\\szell\\OneDrive\\Desktop\\NBA_Per75\\data\\playoff_peak_v2.json"),
        ]
        found = next((p for p in candidates if p.exists()), None)
        if found is not None:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(found, CACHE)
            print("COPIED EXISTING PLAYOFF PEAK CACHE:", found)
        else:
            # If no previous cache exists, build it from the bundled builder.
            builder = ROOT / "build_playoff_peak_cache_v2.py"
            if not builder.exists():
                raise RuntimeError(
                    f"Cache not found: {CACHE}\n"
                    "No existing cache was found and the bundled peak builder is missing."
                )
            print("No existing cache found. Run build_playoff_peak_cache_v2.py first.")
            raise RuntimeError("PLAYOFF_PEAK_CACHE_MISSING")
    payload=json.loads(CACHE.read_text(encoding="utf-8"))
    rows=payload.get("rows",[])
    if not rows:
        raise RuntimeError("Cache contains zero playoff peak rows.")

    stats=sorted({k for r in rows for k,v in (r.get("statistics") or {}).items() if v is not None})
    for stat in stats:
        values=[]
        for r in rows:
            try:
                v=float((r.get("statistics") or {}).get(stat))
                if math.isfinite(v): values.append(v)
            except (TypeError,ValueError): pass
        for r in rows:
            try:
                target=float((r.get("statistics") or {}).get(stat))
                if not math.isfinite(target): continue
            except (TypeError,ValueError): continue
            r.setdefault("percentiles",{})[stat]=pct(values,target,stat in LOWER)

    sdi=[]
    for r in rows:
        try:
            v=float(r.get("sdi"))
            if math.isfinite(v): sdi.append(v)
        except (TypeError,ValueError): pass
    for r in rows:
        try:
            target=float(r.get("sdi"))
            if math.isfinite(target):
                r["sdi_percentile"]=pct(sdi,target,False)
        except (TypeError,ValueError): pass

    payload["version"]="playoff_peak_v3_percentiles"
    payload["percentiles_precomputed"]=True
    payload["player_count"]=len(rows)
    CACHE.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8")

    complete=sum(1 for r in rows if len(r.get("percentiles",{}))>=len(r.get("statistics",{})))
    print("="*80)
    print("PLAYOFF PEAK PERCENTILE REPAIR COMPLETE")
    print("="*80)
    print("Players:",len(rows))
    print("Complete percentile maps:",complete)
    print("Cache:",CACHE)
    print("This repair only reads the existing cache; it does not recalculate peak windows.")

if __name__=="__main__":
    main()
