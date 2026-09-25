from pathlib import Path
import os, json, re, io, pandas as pd, numpy as np

HERE=Path(__file__).resolve()
ROOT=Path(os.environ.get("NBA_PER75_ROOT",r"C:\Users\szell\OneDrive\Desktop\NBA_Per75"))
OUT=HERE.parent/"cache"; OUT.mkdir(parents=True,exist_ok=True)

def norm(s):return re.sub(r"[^a-z0-9]","",str(s).lower())
def find_col(cols,names):
    wanted={norm(n) for n in names}
    for c in cols:
        if norm(c) in wanted:return c
    return None

def duplicate_factor_col(cols,names):
    # Prefer explicitly labeled opponent/defensive columns. Otherwise use the
    # second physical occurrence (pandas commonly exposes it as .1).
    for c in cols:
        n=norm(c); raw=str(c).lower()
        if ("opp" in n or "opponent" in n or "def" in n or "defensive" in n) and any(x in n for x in ("efg","tov")):
            return c
    wanted={norm(n) for n in names}
    seen=0
    for c in cols:
        n=norm(c)
        if n in wanted:
            seen+=1
            if seen==2:return c
        elif n.endswith("1") and n[:-1] in wanted:
            return c
    return None


BREF_TEAM_DEFENSE_CACHE=OUT/"bref_team_defense_four_factors_v1.json"

def bref_key(v): return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",str(v).replace("*","")).strip().lower())

def flat_cols(cols):
    out=[]
    for c in cols:
        if isinstance(c,tuple):
            out.append(" | ".join(str(x).strip() for x in c if str(x).strip() and str(x).strip().lower()!="nan"))
        else: out.append(str(c).strip())
    return out

def parse_bref_adv(html):
    tables=[]
    try: tables.extend(pd.read_html(io.StringIO(html)))
    except Exception: pass
    for comment in re.findall(r"<!--(.*?)-->",html,re.S):
        if "Defense Four Factors" not in comment: continue
        try: tables.extend(pd.read_html(io.StringIO(comment)))
        except Exception: pass
    for tbl in tables:
        flat=[x.lower() for x in flat_cols(tbl.columns)]
        team=next((i for i,x in enumerate(flat) if x in ("team","tm") or x.endswith("| team") or x.endswith("| tm")),None)
        efg=[i for i,x in enumerate(flat) if re.search(r"(^|\|)\s*efg%\s*(\.1)?$",x)]
        tov=[i for i,x in enumerate(flat) if re.search(r"(^|\|)\s*tov%\s*(\.1)?$",x)]
        if team is None or len(efg)<2 or len(tov)<2: continue
        z=pd.DataFrame({"team":tbl.iloc[:,team].astype(str),
                        "opp_efgpct":pd.to_numeric(tbl.iloc[:,efg[-1]],errors="coerce"),
                        "opp_tovpct":pd.to_numeric(tbl.iloc[:,tov[-1]],errors="coerce")})
        z=z[~z.team.str.lower().isin(["league average","nan",""])]
        if len(z): return z
    return None

def fetch_bref(season,stype):
    m=re.search(r"(\d{4})$",str(season))
    if not m:return {}
    year=int(m.group(1))
    url=(f"https://www.basketball-reference.com/playoffs/NBA_{year}.html"
         if stype=="Playoffs" else
         f"https://www.basketball-reference.com/leagues/NBA_{year}.html")
    try:
        from urllib.request import Request,urlopen
        with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 NBA PER-75"}),timeout=30) as r:
            z=parse_bref_adv(r.read().decode("utf-8","ignore"))
        if z is None:return {}
        return {bref_key(x.team):{"opp_efgpct":float(x.opp_efgpct) if pd.notna(x.opp_efgpct) else None,
                                  "opp_tovpct":float(x.opp_tovpct) if pd.notna(x.opp_tovpct) else None}
                for _,x in z.iterrows()}
    except Exception as e:
        print("BRef",stype,season,"failed:",e); return {}

def augment(rows_by_type):
    # Team analytics are intentionally local-source only.  The prior BRef
    # augmentation could parse duplicate eFG%/TOV% columns incorrectly and
    # overwrite the team's offensive values with opponent values.  Opponent
    # fields are preserved from the canonical local source/cache; no network
    # request is required to build this cache.
    return rows_by_type

def find_source():
    files=[]
    for p in ROOT.rglob("*.csv"):
        n=p.name.lower()
        if any(x in n for x in ["team","franchise"]):files.append(p)
    for p in files+list(ROOT.rglob("*.csv")):
        try:
            h=pd.read_csv(p,nrows=0,low_memory=False)
            cols=list(h.columns)
            t=find_col(cols,["Team","Team_Abbreviation","TeamAbbreviation","Tm","Team_Name"])
            s=find_col(cols,["Season","season"])
            o=find_col(cols,["ORtg","ORTG","OffRtg","Offensive_Rating"])
            d=find_col(cols,["DRtg","DRTG","DefRtg","Defensive_Rating"])
            pace=find_col(cols,["Pace","PACE"])
            if t and s and o and d and pace:return p
        except Exception:pass
    raise RuntimeError("No canonical team-season CSV with Team, Season, ORtg, DRtg and Pace was found.")

f=find_source()
h=pd.read_csv(f,nrows=0,low_memory=False)
cols=h.columns
C={
"team":find_col(cols,["Team","Team_Abbreviation","TeamAbbreviation","Tm","Team_Name"]),
"season":find_col(cols,["Season","season"]),
"ortg":find_col(cols,["ORtg","ORTG","OffRtg","Offensive_Rating"]),
"drtg":find_col(cols,["DRtg","DRTG","DefRtg","Defensive_Rating"]),
"pace":find_col(cols,["Pace","PACE"]),
"fgm":find_col(cols,["FG","FGM","FGM_raw","Field Goals Made"]),
"fga":find_col(cols,["FGA","FGA_raw","Field Goal Attempts"]),
"threepm":find_col(cols,["3P","3PM","3PM_raw","Three Pointers Made"]),
"tov":find_col(cols,["TOV","TOV_raw","Turnovers"]),
"fta":find_col(cols,["FTA","FTA_raw","Free Throw Attempts"]),
"rortg":find_col(cols,["rORtg","rORTG","Relative_ORtg","Relative_ORTG"]),
"rdrtg":find_col(cols,["rDRtg","rDRTG","Relative_DRtg","Relative_DRTG"]),
"nrtg":find_col(cols,["NRtg","NRTG","Net_Rtg","NetRtg","NetRating"]),
"pts75":find_col(cols,["PTS_per75","PTS/75","PTS_per_75","Points_per75"]),
"tspct":find_col(cols,["TS_pct","TS%","TS_PCT"]),
"efgpct":find_col(cols,["eFG_pct","eFG%","EFG_PCT"]),
"threepar":find_col(cols,["3PAr","3PA_rate","ThreePA_Rate"]),
"tovpct":find_col(cols,["TOV_pct","TOV%","TOV_PCT"]),
"orbpct":find_col(cols,["ORB_pct","ORB%","ORB_PCT"]),
"ftr":find_col(cols,["FTr","FT_Rate","FTR"]),
"opp_tovpct":find_col(cols,["Opp_TOV_pct","Opp TOV%","Opponent_TOV_pct","Opponent TOV%","OppTOV%","Def_TOV_pct","Def TOV%","Defensive_TOV_pct","Defensive TOV%"]),
"opp_efgpct":find_col(cols,["Opp_eFG_pct","Opp eFG%","Opponent_eFG_pct","Opponent eFG%","OppeFG%","Def_eFG_pct","Def eFG%","Defensive_eFG_pct","Defensive eFG%"]),
}
# Basketball-Reference league Advanced Stats exports can flatten the two
# Four-Factor groups into duplicate headers. Pandas then names the defensive
# copies e.g. eFG%.1 / TOV%.1. Capture those as the opponent fields.
if not C["opp_tovpct"]:
    C["opp_tovpct"]=duplicate_factor_col(cols,["TOV_pct","TOV%","TOV_PCT"])
if not C["opp_efgpct"]:
    C["opp_efgpct"]=duplicate_factor_col(cols,["eFG_pct","eFG%","EFG_PCT"])

wanted=list(dict.fromkeys(x for x in C.values() if x))
d=pd.read_csv(f,usecols=wanted,low_memory=False)
d[C["team"]]=d[C["team"]].astype(str).str.strip()
d=d[d[C["team"]].notna() & ~d[C["team"]].isin(["","nan","None","TOT","Total"])]
for col in wanted:
    if col not in [C["team"],C["season"]]:d[col]=d[col].map(lambda v: float(str(v).strip().rstrip("%")) if str(v).strip().rstrip("%") not in ("", "nan", "None") else np.nan)
rows=[]
for (tm,se),g in d.groupby([C["team"],C["season"]],sort=False):
    r={"team":str(tm),"season":str(se)}
    for k,col in C.items():
        if k in ("team","season") or not col:continue
        v=g[col].dropna()
        if len(v):r[k]=float(v.mean())
    # Canonical local formulas for offensive Four Factors.
    try:
        fgm=float(r.get("fgm")); fga=float(r.get("fga")); threepm=float(r.get("threepm"))
        if fga>0:r["efgpct"]=(fgm+0.5*threepm)/fga
    except Exception:pass
    try:
        tov=float(r.get("tov")); fga=float(r.get("fga")); fta=float(r.get("fta")); den=fga+0.44*fta+tov
        if den>0:r["tovpct"]=tov/den
    except Exception:pass
    rows.append(r)
rows_by_type={"Regular Season":rows}
rows_by_type=augment(rows_by_type)
rows=rows_by_type["Regular Season"]
by={}
for r in rows:by.setdefault(r["season"],[]).append(r)
for rs in by.values():
    mo=np.mean([r["ortg"] for r in rs if r.get("ortg") is not None])
    md=np.mean([r["drtg"] for r in rs if r.get("drtg") is not None])
    for r in rs:
        if r.get("nrtg") is None and r.get("ortg") is not None and r.get("drtg") is not None:r["nrtg"]=r["ortg"]-r["drtg"]
        if r.get("rortg") is None and r.get("ortg") is not None:r["rortg"]=r["ortg"]-mo
        if r.get("rdrtg") is None and r.get("drtg") is not None:r["rdrtg"]=r["drtg"]-md
payload={"version":23,"source":str(f),"rows":rows,
"seasons":sorted({r["season"] for r in rows},reverse=True),
"stats":[
{"label":"Relative DRtg","key":"rdrtg","direction":"lower"},
{"label":"Relative ORtg","key":"rortg","direction":"higher"},
{"label":"NRtg","key":"nrtg","direction":"higher"},
{"label":"Pace","key":"pace","direction":"higher"},
{"label":"ORtg","key":"ortg","direction":"higher"},
{"label":"DRtg","key":"drtg","direction":"lower"},
{"label":"PTS/75","key":"pts75","direction":"higher"},
{"label":"TS%","key":"tspct","direction":"higher"},
{"label":"eFG%","key":"efgpct","direction":"higher"},
{"label":"3PAr","key":"threepar","direction":"higher"},
{"label":"TOV%","key":"tovpct","direction":"lower"},
{"label":"ORB%","key":"orbpct","direction":"higher"},
{"label":"FTr","key":"ftr","direction":"higher"},
{"label":"Opponent TOV%","key":"opp_tovpct","direction":"higher"},
{"label":"Opponent eFG%","key":"opp_efgpct","direction":"lower"}]}
(OUT/"team_analytics_v1.json").write_text(json.dumps(payload,separators=(",",":")),encoding="utf-8")
print("TEAM ANALYTICS PRECOMPUTE COMPLETE")
print("Source:",f)
print("Team-seasons:",len(rows))
print("Cache:",OUT/"team_analytics_v1.json")
