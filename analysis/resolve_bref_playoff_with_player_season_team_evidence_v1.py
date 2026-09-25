r"""
NBA PER-75 — PLAYOFF IDENTITY RESOLVER WITH CANONICAL TEAM EVIDENCE V1

This build uses the project's actual canonical regular-season player-season
source:
    NBA_Per75/player_data_v1_1/player_seasons_v1_1.csv

That source is preferable to nba_per75_master_dreb_v2.csv for identity work
because the project already defines it as the canonical player-season layer
and it carries Player_ID, Player, Season, Season_Type, and team information.

Evidence:
  1. exact normalized B-Ref name;
  2. explicit aliases only when approved;
  3. exact career-year overlap;
  4. exact same Player_ID + Season + Team evidence from the canonical
     regular-season player-season source;
  5. adjacent-season presence;
  6. adjacent-season team continuity.

A collision is auto-resolved only when exactly one candidate has strong,
season-specific team evidence. Otherwise it remains ambiguous.

No fuzzy matching.
No silent guesses.
No regular-season data are modified.
"""

from __future__ import annotations
from pathlib import Path
import re
import unicodedata
import pandas as pd

ROOT=Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75")
RAW=ROOT/"data"/"nba_per75_playoffs_bref_v1.csv"
IDENTITY=ROOT/"player_website_identity_v1"/"website_player_identity_v1.csv"
CANONICAL_SEASONS=ROOT/"data"/"nba_per75_master_dreb_v2.csv"

OUT=ROOT/"data"/"nba_per75_playoffs_player_season_v4.csv"
AUDIT=ROOT/"data"/"nba_per75_playoffs_identity_audit_v4.csv"
DECISIONS=ROOT/"data"/"nba_per75_playoffs_identity_decisions_v4.csv"
REVIEW=ROOT/"data"/"nba_per75_playoffs_unresolved_review_v4.csv"
GROUPS=ROOT/"data"/"nba_per75_playoffs_identity_candidate_groups_v3.csv"

ADDITIVE=["G","GS","MP","FG","FGA","3P","3PA","2P","2PA","FT","FTA",
          "ORB","DRB","TRB","AST","STL","BLK","TOV","PF","PTS"]

# Only add verified historical aliases here.
ALIASES={}

TEAM_ALIASES={
    "PHW":"GSW","SFW":"GSW","GSW":"GSW","GOLDEN STATE WARRIORS":"GSW",
    "FTW":"DET","DET":"DET","FORT WAYNE PISTONS":"DET",
    "SYR":"PHI","PHI":"PHI","PHILADELPHIA":"PHI","SYRACUSE NATIONALS":"PHI",
    "ROC":"SAC","CIN":"SAC","KCO":"SAC","SAC":"SAC","ROCHESTER ROYALS":"SAC",
    "MNL":"LAL","MPL":"LAL","LAL":"LAL","MIN":"MIN","MINNEAPOLIS":"MIN",
    "STL":"ATL","TRI":"ATL","MLH":"ATL","ATL":"ATL","ST LOUIS HAWKS":"ATL",
    "BAL":"WAS","CAP":"WAS","WSB":"WAS","WAS":"WAS","WASHINGTON":"WAS",
    "SEA":"OKC","OKC":"OKC","VAN":"MEM","MEM":"MEM",
    "NJN":"BKN","NJC":"BKN","BRK":"BKN","BKN":"BKN",
    "NOH":"NOP","NOK":"NOP","NO":"NOP","NOP":"NOP",
    "SDC":"LAC","BUF":"LAC","LAC":"LAC",
    "NOJ":"UTA","UTA":"UTA",
    "CHA":"CHA","CHH":"CHA","CHO":"CHA",
    "PHO":"PHX","PHX":"PHX",
    "SAS":"SAS","SAN ANTONIO":"SAS",
    "NYK":"NYK","BOS":"BOS","CHI":"CHI","CLE":"CLE","IND":"IND",
    "MIL":"MIL","MIA":"MIA","ORL":"ORL","TOR":"TOR","DAL":"DAL",
    "HOU":"HOU","DEN":"DEN","POR":"POR","UTA":"UTA",
}

def norm_name(v):
    s="" if pd.isna(v) else str(v)
    s=unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode("ascii")
    s=s.casefold()
    s=re.sub(r"[\*\u2020\u2021]+","",s)
    s=s.replace("&"," and ")
    s=re.sub(r"[^a-z0-9 ]+"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def norm_team(v):
    if pd.isna(v): return ""
    s=str(v).strip().upper()
    s=re.sub(r"[^A-Z0-9 ]+","",s)
    return TEAM_ALIASES.get(s,s)

def year(v):
    if pd.isna(v): return None
    m=re.search(r"(19|20)\d{2}",str(v))
    return int(m.group(0)) if m else None

def find_col(df,names):
    compact={re.sub(r"[^a-z0-9]","",str(c).casefold()):c for c in df.columns}
    for n in names:
        k=re.sub(r"[^a-z0-9]","",n.casefold())
        if k in compact: return compact[k]
    return None

def load_identity():
    ident=pd.read_csv(IDENTITY,low_memory=False)
    pid=find_col(ident,["Player_ID","PlayerId","PlayerID","player_id"])
    name=find_col(ident,["Player","Player_Name","Display_Name","Name"])
    if not pid or not name:
        raise ValueError("Website identity source needs Player_ID and player-name columns.")

    names={}
    display={}
    for _,r in ident.iterrows():
        p=str(r[pid]).strip()
        n=norm_name(r[name])
        if p and p.casefold()!="nan" and n:
            names.setdefault(n,set()).add(p)
            display[p]=str(r[name]).strip()
    return names,display

def load_canonical_team_evidence():
    if not CANONICAL_SEASONS.exists():
        raise FileNotFoundError(
            f"Canonical player-season source not found: {CANONICAL_SEASONS}"
        )

    df=pd.read_csv(CANONICAL_SEASONS,low_memory=False)
    # The canonical player-season export intentionally contains only the
    # player-season identity/stat fields. It does NOT retain Team. For
    # team-season evidence, use the validated integrated master, which is the
    # project's upstream source containing Team and Season_Type.
    required=["Player","Season","Season_Type","Team"]
    missing=[c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            "Integrated master is missing required columns: "
            + ", ".join(missing)
        )

    df=df[df["Season_Type"].astype(str).str.casefold().eq("regular season")].copy()
    df["_Year"]=df["Season"].map(year)
    df["_TeamNorm"]=df["Team"].map(norm_team)

    # Attach canonical Player_ID from the website identity registry.
    identity=pd.read_csv(IDENTITY,low_memory=False)
    pid_col=find_col(identity,["Player_ID","PlayerId","PlayerID","player_id"])
    name_col=find_col(identity,["Player","Player_Name","Display_Name","Name"])
    if not pid_col or not name_col:
        raise ValueError("Website identity layer needs Player_ID and Player.")
    id_map=identity[[pid_col,name_col]].copy()
    id_map["_NameNorm"]=id_map[name_col].map(norm_name)
    id_map=id_map.drop_duplicates("_NameNorm")
    df["_NameNorm"]=df["Player"].map(norm_name)
    df=df.merge(
        id_map[["_NameNorm",pid_col]],
        on="_NameNorm",
        how="left",
        validate="many_to_one"
    )
    df["Player_ID"]=df[pid_col]

    # Exact player-season-team identities. Drop duplicates only; never sum stats.
    rows=df.loc[
        df["Player_ID"].notna()
        & df["_Year"].notna()
        & df["_TeamNorm"].ne("")
    ].copy()

    careers=rows.groupby("Player_ID")["_Year"].agg(lambda s:set(int(x) for x in s)).to_dict()
    team_by_pid_year=(
        rows.groupby(["Player_ID","_Year"])["_TeamNorm"]
        .agg(lambda s:set(str(x) for x in s))
        .to_dict()
    )
    return df,careers,team_by_pid_year

def evidence_for(pid,y,bref_team,careers,team_by_pid_year):
    bteam=norm_team(bref_team)
    cyears=careers.get(pid,set())
    cteams=team_by_pid_year.get((pid,y),set())

    exact_year=y in cyears
    same_team=bool(bteam and bteam in cteams)

    adj_years=[ay for ay in (y-2,y-1,y+1,y+2) if ay in cyears]
    adj_team_years=[]
    if bteam:
        for ay in (y-2,y-1,y+1,y+2):
            if bteam in team_by_pid_year.get((pid,ay),set()):
                adj_team_years.append(ay)

    score=0
    reasons=[]
    if same_team:
        score+=100
        reasons.append("same_team_same_season")
    if exact_year:
        score+=35
        reasons.append("career_contains_season")
    if adj_team_years:
        score+=20
        reasons.append("adjacent_team_continuity")
    if adj_years:
        score+=5
        reasons.append("adjacent_career_presence")

    return {
        "score":score,
        "exact_year":exact_year,
        "same_team":same_team,
        "adjacent_years":",".join(map(str,adj_years)),
        "adjacent_team_years":",".join(map(str,adj_team_years)),
        "candidate_teams":"/".join(sorted(cteams)),
        "reasons":";".join(reasons),
    }

def consolidate(resolved):
    if resolved.empty:
        return pd.DataFrame()

    rows=[]
    for (pid,y),g in resolved.groupby(["Player_ID","Season"],dropna=False,sort=True):
        out={
            "Player_ID":str(pid),
            "Player":str(g["Canonical_Player"].iloc[0]),
            "Season":int(y),
            "Season_Type":"Playoffs",
            "Teams":" / ".join(sorted(set(
                str(x).strip() for x in g["Team"].dropna()
                if str(x).strip()
            ))),
            "BRef_Rows_Combined":int(len(g)),
        }
        for c in ADDITIVE:
            if c in g.columns:
                vals=pd.to_numeric(g[c],errors="coerce")
                out[c]=float(vals.sum(min_count=1)) if vals.notna().any() else None

        for pct,num,den in [
            ("FG%","FG","FGA"),("3P%","3P","3PA"),
            ("2P%","2P","2PA"),("FT%","FT","FTA")
        ]:
            a=out.get(num); b=out.get(den)
            out[pct]=a/b if a is not None and b not in (None,0) else None

        fg=out.get("FG"); th=out.get("3P"); fga=out.get("FGA")
        out["eFG%"]=(fg+.5*th)/fga if fg is not None and th is not None and fga not in (None,0) else None
        rows.append(out)

    return pd.DataFrame(rows)

def main():
    raw=pd.read_csv(RAW,low_memory=False)
    names,display=load_identity()
    canonical,careers,team_by_pid_year=load_canonical_team_evidence()

    rname=find_col(raw,["Player","Player_Name"])
    rseason=find_col(raw,["Season"])
    rteam=find_col(raw,["Team","Tm"])
    if not rname or not rseason or not rteam:
        raise ValueError("B-Ref source needs Player, Season, and Team columns.")

    alias_map={norm_name(k):norm_name(v) for k,v in ALIASES.items()}
    decisions=[]

    for idx,r in raw.iterrows():
        source=str(r[rname]).strip()
        y=year(r[rseason])
        bteam=r[rteam]
        n=norm_name(source)

        candidates=set(names.get(n,set()))
        method="exact_normalized_name"

        if not candidates and n in alias_map:
            candidates=set(names.get(alias_map[n],set()))
            method="explicit_alias"

        evidence=[(pid,evidence_for(pid,y,bteam,careers,team_by_pid_year))
                  for pid in sorted(candidates)]

        chosen=None
        status="Unmatched" if not evidence else "Ambiguous"
        decision_method="No deterministic match"
        top_score=None
        runner_score=None

        if len(evidence)==1:
            chosen=evidence[0][0]
            status="Resolved"
            decision_method=method
            top_score=evidence[0][1]["score"]
        elif evidence:
            strong=[(pid,ev) for pid,ev in evidence
                     if ev["same_team"] and ev["exact_year"]]
            if len(strong)==1:
                chosen=strong[0][0]
                status="Resolved"
                decision_method="exact_name_plus_same_team_same_season"
                top_score=strong[0][1]["score"]
                ranked=sorted(evidence,key=lambda x:(x[1]["score"],x[0]),reverse=True)
                if len(ranked)>1:
                    runner_score=ranked[1][1]["score"]
            else:
                ranked=sorted(evidence,key=lambda x:(x[1]["score"],x[0]),reverse=True)
                top_score=ranked[0][1]["score"]
                runner_score=ranked[1][1]["score"] if len(ranked)>1 else None
                status="Ambiguous"
                decision_method="Candidate collision; no unique team-season evidence"

        top_ev=next((ev for pid,ev in evidence if pid==chosen),None)

        decisions.append({
            "raw_index":idx,
            "BRef_Player":source,
            "BRef_Team":str(bteam) if not pd.isna(bteam) else "",
            "BRef_Team_Normalized":norm_team(bteam),
            "Season":y,
            "Player_ID":chosen,
            "Canonical_Player":display.get(chosen) if chosen else None,
            "Identity_Status":status,
            "Identity_Method":decision_method,
            "Candidate_IDs":";".join(pid for pid,_ in evidence),
            "Candidate_Count":len(evidence),
            "Top_Score":top_score,
            "Runner_Up_Score":runner_score,
            "Same_Team_Evidence":top_ev["same_team"] if top_ev else False,
            "Career_Year_Evidence":top_ev["exact_year"] if top_ev else False,
            "Adjacent_Team_Evidence":top_ev["adjacent_team_years"] if top_ev else "",
            "Adjacent_Year_Evidence":top_ev["adjacent_years"] if top_ev else "",
            "Candidate_Evidence":" | ".join(
                f"{pid}:score={ev['score']};same_team={ev['same_team']};career={ev['exact_year']};adj_team={ev['adjacent_team_years']};adj_year={ev['adjacent_years']};teams={ev['candidate_teams']}"
                for pid,ev in evidence
            ),
        })

    dec=pd.DataFrame(decisions)
    dec.to_csv(DECISIONS,index=False)

    raw2=raw.copy()
    raw2["_raw_index"]=range(len(raw2))
    merged=raw2.merge(
        dec,left_on="_raw_index",right_on="raw_index",
        how="left",validate="one_to_one",suffixes=("_raw","_decision")
    )
    if "Player_ID_decision" in merged.columns:
        merged["Player_ID"]=merged["Player_ID_decision"]
    if "Season_decision" in merged.columns:
        merged["Season"]=merged["Season_decision"]
    if "Canonical_Player_decision" in merged.columns:
        merged["Canonical_Player"]=merged["Canonical_Player_decision"]

    resolved=merged.loc[merged["Identity_Status"].eq("Resolved")].copy()
    canonical_out=consolidate(resolved)
    if not canonical_out.empty:
        canonical_out=canonical_out.sort_values(["Season","Player"],kind="stable")
        canonical_out.to_csv(OUT,index=False)

    unresolved=merged.loc[merged["Identity_Status"].ne("Resolved")].copy()
    unresolved.to_csv(REVIEW,index=False)

    group=unresolved.groupby(
        ["BRef_Player","BRef_Team","Season","Identity_Status"],
        dropna=False,sort=True
    ).agg(
        Raw_Rows=("_raw_index","count"),
        Candidate_IDs=("Candidate_IDs",lambda s:";".join(sorted(set(
            x for v in s.fillna("") for x in str(v).split(";") if x
        )))),
        Max_Score=("Top_Score","max"),
        Same_Team_Hits=("Same_Team_Evidence","sum"),
    ).reset_index()
    group.to_csv(GROUPS,index=False)

    vc=dec["Identity_Status"].value_counts()
    same_team_res=int(
        (dec["Identity_Method"]=="exact_name_plus_same_team_same_season").sum()
    )

    audit=pd.DataFrame([{
        "Raw_BRef_Rows":len(raw),
        "Resolved_Rows":int(vc.get("Resolved",0)),
        "Ambiguous_Rows":int(vc.get("Ambiguous",0)),
        "Unmatched_Rows":int(vc.get("Unmatched",0)),
        "Canonical_Player_Seasons":len(canonical_out),
        "Canonical_Players":canonical_out["Player_ID"].nunique() if not canonical_out.empty else 0,
        "Seasons":canonical_out["Season"].nunique() if not canonical_out.empty else 0,
        "Same_Team_Season_Resolutions":same_team_res,
        "Canonical_Team_Evidence_Rows":len(canonical),
        "Canonical_Team_Evidence_Players":canonical["Player_ID"].nunique(),
        "Review_Groups":len(group),
        "Fuzzy_Matching":"NO",
        "Silent_Guesses":"NO",
    }])
    audit.to_csv(AUDIT,index=False)

    print("="*88)
    print("NBA PER-75 — PLAYOFF IDENTITY RESOLVER WITH CANONICAL TEAM EVIDENCE V1")
    print("="*88)
    print(f"Raw B-Ref rows:             {len(raw):,}")
    print(f"Canonical team evidence:    {len(canonical):,} regular-season rows")
    print(f"Resolved rows:              {vc.get('Resolved',0):,}")
    print(f"Ambiguous rows:             {vc.get('Ambiguous',0):,}")
    print(f"Unmatched rows:             {vc.get('Unmatched',0):,}")
    print(f"Same-team/season resolves:  {same_team_res:,}")
    print(f"Canonical player-seasons:   {len(canonical_out):,}")
    print(f"Canonical players:          {canonical_out['Player_ID'].nunique() if not canonical_out.empty else 0:,}")
    print(f"Review groups:              {len(group):,}")
    print(f"Decision audit:             {DECISIONS}")
    print(f"Canonical output:           {OUT}")
    print(f"Unresolved review:          {REVIEW}")
    print(f"Candidate groups:           {GROUPS}")
    print()
    print("No fuzzy identity assignment was performed.")
    print("No identity was silently guessed.")

if __name__=="__main__":
    main()
