from pathlib import Path
import os, json, re, pandas as pd

HERE=Path(__file__).resolve()
_ESTABLISHED_ROOT=Path(os.environ.get("NBA_PER75_ROOT", r"C:\Users\szell\OneDrive\Desktop\NBA_Per75"))
_ROOT_CANDIDATES=[
    _ESTABLISHED_ROOT,
    HERE.parents[2] / "NBA_Per75",
    HERE.parents[3] / "NBA_Per75",
]
ROOT=next((p for p in _ROOT_CANDIDATES if (p/"data").exists()),_ESTABLISHED_ROOT)
MASTER=ROOT/"data"/"nba_per75_master_v46.csv"
OUT=HERE.parent/"cache"
OUT.mkdir(parents=True,exist_ok=True)

def find_master():
    if MASTER.exists(): return MASTER
    for p in ROOT.rglob("*.csv"):
        if "nba_per75_master" in p.name.lower():
            return p
    raise FileNotFoundError(f"Could not find NBA PER-75 master CSV under {ROOT}")

def pick(cols,cands):
    norm={re.sub(r"[^a-z0-9]","",str(x).lower()):x for x in cols}
    for c in cands:
        k=re.sub(r"[^a-z0-9]","",c.lower())
        if k in norm:return norm[k]
    return None

f=find_master()
h=pd.read_csv(f,nrows=0,low_memory=False)
team=pick(h.columns,["Team","Team_Abbreviation","TeamAbbreviation","Tm","TeamID","Franchise","Team_Name"])
season=pick(h.columns,["Season","season"])
player=pick(h.columns,["Player_Name","Player","Name","player_name"])
pid=pick(h.columns,["Player_ID","PlayerId","PlayerID","player_id"])
mp=pick(h.columns,["MP","Minutes","Minutes_Played"])
pts=pick(h.columns,["PTS","Points"])
if not team or not season:
    raise RuntimeError("Master dataset does not expose Team and Season columns.")

wanted=list(dict.fromkeys([x for x in [team,season,player,pid,mp,pts] if x]))
d=pd.read_csv(f,usecols=wanted,low_memory=False)
d[team]=d[team].astype(str).str.strip()
d=d[d[team].notna() & ~d[team].isin(["","nan","None","TOT","Total"])].copy()
d=d[~d[team].astype(str).str.upper().str.match(r"^(?:2TM|3TM|4TM|TOT|TOTAL)(?:$|[\s_-])",na=False)].copy()

rows=[]
for (tm,se),g in d.groupby([team,season],sort=False):
    rows.append({"team":str(tm),"season":str(se),
                 "player_count":int(g[player].nunique()) if player else int(len(g))})
seasons=sorted({x["season"] for x in rows},key=lambda s: (int(str(s)[:4]) if str(s)[:4].isdigit() else 9999))

# The current canonical source is player regular-season data. Keep both keys
# so the frontend can select Playoffs without forcing an expensive request.
payload={"version":2,"source":str(f),
         "season_types":{
             "Regular Season":{"rows":rows,"seasons":seasons,"count":len(rows)},
             "Playoffs":{"rows":[],"seasons":[]}
         }}
(OUT/"team_index_v1.json").write_text(json.dumps(payload,separators=(",",":")),encoding="utf-8")

# Build compact roster records for instant team-season detail panels.
rosters={}
for (tm,se),g in d.groupby([team,season],sort=False):
    plist=[]
    for _,r in g.iterrows():
        name=r[player] if player else None
        if name is None or pd.isna(name): continue
        plist.append({"player_id":None if not pid or pd.isna(r[pid]) else r[pid],
                      "player_name":str(name),
                      "minutes":None if not mp or pd.isna(r[mp]) else r[mp],
                      "points":None if not pts or pd.isna(r[pts]) else r[pts]})
    rosters[f"Regular Season|||{tm}|||{se}"]={"players":plist}
(OUT/"team_rosters_v1.json").write_text(json.dumps({"version":1,"rosters":rosters},default=str,separators=(",",":")),encoding="utf-8")
print("TEAM INDEX PRECOMPUTE COMPLETE")
print("Master:",f)
print("Team-season rows:",len(rows))
print("Seasons:",len(seasons))
print("Index:",OUT/"team_index_v1.json")
print("Rosters:",OUT/"team_rosters_v1.json")
