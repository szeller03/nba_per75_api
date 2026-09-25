from pathlib import Path
import os, json, re, pandas as pd

HERE=Path(__file__).resolve(); OUT=HERE.parent/"cache"
CACHE=OUT/"team_analytics_v1.json"
ROOT=Path(os.environ.get("NBA_PER75_ROOT", str(HERE.parents[1])))

def norm(s): return re.sub(r"[^a-z0-9]","",str(s).lower())
def find(cols,names):
    w={norm(x) for x in names}
    return next((c for c in cols if norm(c) in w),None)

def source():
    p=ROOT/"data"/"nba_per75_team_master_enriched.csv"
    if p.exists(): return p
    p=ROOT/"data"/"nba_per75_team_master.csv"
    if p.exists(): return p
    raise FileNotFoundError("Canonical team master not found")

f=source(); h=pd.read_csv(f,nrows=0,low_memory=False); cols=list(h.columns)
team=find(cols,["Team","Team_Abbreviation","TeamAbbreviation","Tm","Team_Name"])
season=find(cols,["Season","season"]); st=find(cols,["Season_Type","SeasonType","Season Type","Type","League_Type"])
fgm=find(cols,["FG","FGM","FG_raw","FGM_raw","Field Goals Made","FieldGoalsMade"])
fga=find(cols,["FGA","FGA_raw","Field Goal Attempts","FieldGoalAttempts"])
threem=find(cols,["3P","3PM","3P_raw","3PM_raw","Three Pointers Made","ThreePointersMade"])
tov=find(cols,["TOV","TOV_raw","Turnovers","turnovers"])
fta=find(cols,["FTA","FTA_raw","Free Throw Attempts","FreeThrowAttempts"])
efg_col=find(cols,["eFG_pct","eFG%","EFG_PCT","EFG_pct"])
tovpct_col=find(cols,["TOV_pct","TOV%","TOV_PCT"])
missing=[name for name,val in [("team",team),("season",season)] if not val]
if missing: raise RuntimeError("Canonical team source is missing required identity columns: "+", ".join(missing))
# Some canonical exports already contain the correctly derived offensive Four Factors
# but use a schema without the underlying counting-stat columns. In that case use
# those canonical offensive fields directly rather than stopping or consulting BRef.
if not all([fgm,fga,threem,tov,fta]) and not (efg_col and tovpct_col):
    raise RuntimeError("Canonical team source lacks both the raw counting inputs and the canonical offensive eFG%/TOV% fields. Available columns: " + ", ".join(map(str, cols)))
use=list(dict.fromkeys([team,season]+([st] if st else [])+[x for x in [fgm,fga,threem,tov,fta,efg_col,tovpct_col] if x]))
d=pd.read_csv(f,usecols=use,low_memory=False)
for c in [fgm,fga,threem,tov,fta,efg_col,tovpct_col]:
    if c: d[c]=pd.to_numeric(d[c],errors="coerce")
out=[]
for keys,g in d.groupby([team,season]+([st] if st else []),dropna=False):
    vals={}
    for key,col in [("fgm",fgm),("fga",fga),("3pm",threem),("tov",tov),("fta",fta)]:
        vals[key]=g[col].sum(min_count=1) if col else None
    if all(pd.notna(vals[x]) for x in ("fgm","fga","3pm")) and vals["fga"]>0:
        efg_value=(vals["fgm"]+0.5*vals["3pm"])/vals["fga"]
    elif efg_col:
        efg_value=g[efg_col].mean()
    else:
        efg_value=None
    den=vals["fga"]+0.44*vals["fta"]+vals["tov"] if all(pd.notna(vals[x]) for x in ("fga","fta","tov")) else None
    tov_pct=vals["tov"]/den if den and den>0 else (g[tovpct_col].mean() if tovpct_col else None)
    keyvals=list(keys) if isinstance(keys,tuple) else [keys]
    rec={"team":str(keyvals[0]),"season":str(keyvals[1]),"efgpct":efg_value,"tovpct":tov_pct}
    if st: rec["season_type"]=str(keyvals[2])
    out.append(rec)

if CACHE.exists():
    payload=json.loads(CACHE.read_text(encoding="utf-8"))
else: payload={"version":20,"season_types":{}}
for rec in out:
    typ=rec.get("season_type","Regular Season")
    rows=payload.setdefault("season_types",{}).setdefault(typ,{"rows":[]}).get("rows",[])
    hit=next((r for r in rows if str(r.get("team"))==rec["team"] and str(r.get("season"))==rec["season"]),None)
    if hit is not None:
        if rec["efgpct"] is not None: hit["efgpct"]=rec["efgpct"]
        if rec["tovpct"] is not None: hit["tovpct"]=rec["tovpct"]
    else: rows.append(rec)
payload["version"]=20
def _clean_json(v):
    if isinstance(v, dict): return {k:_clean_json(x) for k,x in v.items()}
    if isinstance(v, list): return [_clean_json(x) for x in v]
    if isinstance(v, float) and pd.isna(v): return None
    return v
payload=_clean_json(payload)
CACHE.write_text(json.dumps(payload,separators=(",",":"),allow_nan=False),encoding="utf-8")
print("Repaired offensive eFG% and TOV% locally from canonical counting stats.")
print("No Basketball-Reference requests were made.")
print("Rows repaired:",len(out))
print("Cache:",CACHE)
