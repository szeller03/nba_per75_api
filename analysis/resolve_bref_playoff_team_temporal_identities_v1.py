r"""
NBA PER-75 — BASKETBALL-REFERENCE PLAYOFF TEAM/TEMPORAL IDENTITY RESOLVER V1

This is the next deterministic identity layer after V22.2.

Evidence used, in order:
  1. exact normalized B-Ref name;
  2. explicit aliases (only if approved);
  3. exact career-year overlap;
  4. regular-season team overlap for the same player + season;
  5. adjacent-season presence;
  6. adjacent-season team continuity.

A candidate is auto-resolved only when the evidence produces one unique
winner with a strong, explainable score. All decisions carry an audit trail.

No fuzzy matching.
No probabilistic guessing.
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
MASTER=ROOT/"data"/"nba_per75_master_dreb_v2.csv"

OUT=ROOT/"data"/"nba_per75_playoffs_player_season_v3.csv"
AUDIT=ROOT/"data"/"nba_per75_playoffs_identity_audit_v3.csv"
REVIEW=ROOT/"data"/"nba_per75_playoffs_unresolved_review_v3.csv"
DECISIONS=ROOT/"data"/"nba_per75_playoffs_identity_decisions_v3.csv"
GROUPS=ROOT/"data"/"nba_per75_playoffs_identity_candidate_groups_v2.csv"

ADDITIVE=["G","GS","MP","FG","FGA","3P","3PA","2P","2PA","FT","FTA",
          "ORB","DRB","TRB","AST","STL","BLK","TOV","PF","PTS"]

ALIASES={}

# Historical/current franchise abbreviations. This is only used to normalize
# equivalent team labels, not to identify a player by team alone.
TEAM_ALIASES={
    "BOS":"BOS","CELTICS":"BOS",
    "NYK":"NYK","NY KNICKS":"NYK","KNICKS":"NYK",
    "PHW":"GSW","SFW":"GSW","GSW":"GSW","GOLDEN STATE":"GSW","WARRIORS":"GSW",
    "LAL":"LAL","LAA":"LAL","MIN":"MIN","MPLS":"MIN","MINNEAPOLIS":"MIN",
    "SYR":"SYR","PHI":"PHI","SIXERS":"PHI",
    "ROC":"ROC","SAC":"SAC","CIN":"CIN","KCO":"KCO","KCK":"KCK",
    "STL":"STL","MIL":"MIL","CHI":"CHI","DET":"DET","FORT WAYNE":"DET",
    "BAL":"BAL","CAP":"WAS","WSB":"WAS","WAS":"WAS","WASHINGTON":"WAS",
    "ATL":"ATL","STLHAWKS":"ATL","HAWKS":"ATL",
    "SEA":"SEA","OKC":"OKC","THUNDER":"OKC",
    "POR":"POR","DEN":"DEN","UTA":"UTA","NOH":"NOP","NOP":"NOP",
    "CHA":"CHA","CHH":"CHA","CHO":"CHA",
    "VAN":"MEM","MEM":"MEM","TOR":"TOR",
    "ORL":"ORL","MIA":"MIA","CLE":"CLE","IND":"IND",
    "NJN":"BKN","BKN":"BKN","BRK":"BKN",
    "SAS":"SAS","SAN ANTONIO":"SAS",
    "DAL":"DAL","HOU":"HOU","PHX":"PHX","PHO":"PHX",
    "LAC":"LAC","SDC":"LAC","BUF":"LAC",
    "NO":"NOP","NOK":"NOP","NOLA":"NOP",
    "CHS":"CHI","WAS":"WAS",
}

def norm_name(v):
    s="" if pd.isna(v) else str(v)
    s=unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode("ascii")
    s=s.casefold()
    s=re.sub(r"[\*\u2020\u2021]+","",s)
    s=s.replace("&"," and ")
    s=re.sub(r"[^a-z0-9 ]+"," ",s)
    # Do not remove suffixes for identity scoring unless the source itself
    # omits them; normalized identity registry follows the same convention.
    s=re.sub(r"\s+"," ",s).strip()
    return s

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
    norm={re.sub(r"[^a-z0-9]","",str(c).casefold()):c for c in df.columns}
    for n in names:
        k=re.sub(r"[^a-z0-9]","",n.casefold())
        if k in norm:return norm[k]
    return None

def build_identity(ident):
    iid=find_col(ident,["Player_ID","PlayerId","PlayerID","player_id"])
    iname=find_col(ident,["Player","Player_Name","Display_Name","Name"])
    if not iid or not iname: raise ValueError("Identity source needs Player_ID and player-name columns.")
    names={}
    display={}
    for _,r in ident.iterrows():
        pid=str(r[iid]).strip()
        n=norm_name(r[iname])
        if pid and n:
            names.setdefault(n,set()).add(pid)
            display[pid]=str(r[iname]).strip()
    return iid,iname,names,display

def build_master_evidence(master, ident):
    mid=find_col(master,["Player_ID","PlayerId","PlayerID","player_id"])
    mname=find_col(master,["Player","Player_Name","Display_Name","Name"])
    mseason=find_col(master,["Season","season"])
    mteam=find_col(master,["Team","Tm","TEAM_ABBREVIATION","Team_Abbreviation","Team_Name"])
    careers={}
    team_by_pid_year={}
    years_by_pid={}

    # Some versions of the regular-season master do not carry the canonical
    # Player_ID/Season field names. The identity registry itself contains an
    # Available_Seasons field, so use that as a safe career-year fallback.
    if not mid or not mseason:
        iid=find_col(ident,["Player_ID","PlayerId","PlayerID","player_id"])
        iseasons=find_col(ident,["Available_Seasons","Available Season Years","Seasons"])
        if iid and iseasons:
            for _,r in ident[[iid,iseasons]].iterrows():
                pid=str(r[iid]).strip()
                if not pid or pid.casefold()=="nan": continue
                yrs=set()
                for token in re.findall(r"(?:19|20)\d{2}",str(r[iseasons])):
                    yrs.add(int(token))
                if yrs:
                    careers[pid]=yrs
                    years_by_pid[pid]=set(yrs)
            # Team evidence is unavailable from this fallback. It remains
            # explicitly absent rather than inferred from a player's name.
            return careers,years_by_pid,team_by_pid_year,None

    cols=[mid,mseason]+([mteam] if mteam else [])
    for _,r in master[cols].iterrows():
        pid=str(r[mid]).strip()
        y=year(r[mseason])
        if not pid or pid.casefold()=="nan" or y is None: continue
        careers.setdefault(pid,set()).add(y)
        years_by_pid.setdefault(pid,set()).add(y)
        if mteam and pd.notna(r[mteam]):
            team_by_pid_year.setdefault((pid,y),set()).add(norm_team(r[mteam]))
    return careers,years_by_pid,team_by_pid_year,mteam

def candidate_evidence(pid,y,bref_team,careers,years_by_pid,team_by_pid_year):
    cyears=careers.get(pid,set())
    cteams=team_by_pid_year.get((pid,y),set())
    bteam=norm_team(bref_team)

    career_exact=y in cyears
    same_team=bool(bteam and bteam in cteams)

    adjacent=[]
    for ay in (y-2,y-1,y+1,y+2):
        if ay in cyears:
            adjacent.append(ay)

    adjacent_team=[]
    if bteam:
        for ay in (y-2,y-1,y+1,y+2):
            if bteam in team_by_pid_year.get((pid,ay),set()):
                adjacent_team.append(ay)

    # Strong evidence hierarchy. Team + exact year is decisive. Exact career
    # year without team is supportive, not enough to break a collision by itself.
    score=0
    reasons=[]
    if same_team:
        score+=100; reasons.append(f"same_team_{y}")
    if career_exact:
        score+=35; reasons.append(f"career_contains_{y}")
    if adjacent_team:
        score+=20; reasons.append("adjacent_team_continuity")
    if adjacent:
        score+=5; reasons.append("adjacent_career_year")

    return {
        "score":score,
        "career_exact":career_exact,
        "same_team":same_team,
        "adjacent_years":",".join(map(str,adjacent)),
        "adjacent_team_years":",".join(map(str,adjacent_team)),
        "candidate_teams":"/".join(sorted(cteams)),
        "reasons":";".join(reasons),
    }

def consolidate(resolved):
    if resolved.empty:return pd.DataFrame()
    rows=[]
    for (pid,y),g in resolved.groupby(["Player_ID","Season"],dropna=False,sort=True):
        out={
            "Player_ID":str(pid),
            "Player":str(g["Canonical_Player"].iloc[0]),
            "Season":int(y),
            "Season_Type":"Playoffs",
            "Teams":" / ".join(sorted(set(
                str(x) for x in g["Team"].dropna().tolist() if str(x).strip()
            ))) if "Team" in g else "",
            "BRef_Rows_Combined":int(len(g)),
        }
        for c in ADDITIVE:
            if c in g:
                v=pd.to_numeric(g[c],errors="coerce")
                out[c]=float(v.sum(min_count=1)) if v.notna().any() else None
        for pct,num,den in [("FG%","FG","FGA"),("3P%","3P","3PA"),
                            ("2P%","2P","2PA"),("FT%","FT","FTA")]:
            a=out.get(num); b=out.get(den)
            out[pct]=a/b if a is not None and b not in (None,0) else None
        fg=out.get("FG"); th=out.get("3P"); fga=out.get("FGA")
        out["eFG%"]=(fg+.5*th)/fga if fg is not None and th is not None and fga not in (None,0) else None
        rows.append(out)
    return pd.DataFrame(rows)

def main():
    raw=pd.read_csv(RAW,low_memory=False)
    ident=pd.read_csv(IDENTITY,low_memory=False)
    master=pd.read_csv(MASTER,low_memory=False)

    rid=find_col(raw,["Player","Player_Name"])
    rseason=find_col(raw,["Season"])
    rteam=find_col(raw,["Team","Tm"])
    if not rid or not rseason:
        raise ValueError("B-Ref source requires Player and Season.")

    iid,iname,names,display=build_identity(ident)
    careers,years_by_pid,team_by_pid_year,mteam=build_master_evidence(master, ident)

    alias_map={norm_name(k):norm_name(v) for k,v in ALIASES.items()}

    decisions=[]
    for idx,r in raw.iterrows():
        source=str(r[rid]).strip()
        y=year(r[rseason])
        bteam=r[rteam] if rteam else ""
        n=norm_name(source)
        candidates=set(names.get(n,set()))
        method="exact_normalized_name"

        if not candidates and n in alias_map:
            candidates=set(names.get(alias_map[n],set()))
            method="explicit_alias"

        # Evaluate every exact-name candidate using the regular-season
        # historical universe.
        evidence=[]
        for pid in sorted(candidates):
            ev=candidate_evidence(pid,y,bteam,careers,years_by_pid,team_by_pid_year)
            evidence.append((pid,ev))

        status="Unmatched"
        chosen=None
        decision_method="No deterministic match"
        top_score=None
        runner_score=None

        if len(evidence)==1:
            chosen=evidence[0][0]
            status="Resolved"
            decision_method=method
            top_score=evidence[0][1]["score"]
        elif evidence:
            ranked=sorted(evidence,key=lambda x:(x[1]["score"],x[0]),reverse=True)
            top_score=ranked[0][1]["score"]
            runner_score=ranked[1][1]["score"] if len(ranked)>1 else None

            # Require strong team+year evidence for collision resolution.
            # A unique same-team exact-year candidate wins decisively.
            strong=[x for x in evidence if x[1]["same_team"] and x[1]["career_exact"]]
            if len(strong)==1:
                chosen=strong[0][0]
                status="Resolved"
                decision_method="exact_name_plus_career_year_plus_same_team"
            else:
                status="Ambiguous"
                decision_method="Candidate collision; insufficient unique evidence"

        top_ev=next((ev for pid,ev in evidence if pid==chosen),None)
        candidate_ids=";".join(pid for pid,_ in evidence)

        d={
            "raw_index":idx,
            "BRef_Player":source,
            "BRef_Team":str(bteam) if not pd.isna(bteam) else "",
            "Season":y,
            "Player_ID":chosen,
            "Canonical_Player":display.get(chosen) if chosen else None,
            "Identity_Status":status,
            "Identity_Method":decision_method,
            "Candidate_IDs":candidate_ids,
            "Top_Score":top_score,
            "Runner_Up_Score":runner_score,
            "Evidence_Reasons":top_ev["reasons"] if top_ev else "",
            "Same_Team_Evidence":top_ev["same_team"] if top_ev else False,
            "Career_Year_Evidence":top_ev["career_exact"] if top_ev else False,
            "Adjacent_Team_Evidence":top_ev["adjacent_team_years"] if top_ev else "",
            "Adjacent_Year_Evidence":top_ev["adjacent_years"] if top_ev else "",
            "Candidate_Evidence":" | ".join(
                f"{pid}:score={ev['score']};same_team={ev['same_team']};career={ev['career_exact']};adj_team={ev['adjacent_team_years']};adj_year={ev['adjacent_years']};teams={ev['candidate_teams']}"
                for pid,ev in evidence
            ),
        }
        decisions.append(d)

    dec=pd.DataFrame(decisions)
    dec.to_csv(DECISIONS,index=False)

    raw2=raw.copy()
    raw2["_raw_index"]=range(len(raw2))
    merged=raw2.merge(dec,left_on="_raw_index",right_on="raw_index",
                      how="left",validate="one_to_one",suffixes=("_raw","_decision"))

    # Canonicalize merged field names.
    if "Player_ID_decision" in merged: merged["Player_ID"]=merged["Player_ID_decision"]
    if "Season_decision" in merged: merged["Season"]=merged["Season_decision"]
    if "Canonical_Player_decision" in merged: merged["Canonical_Player"]=merged["Canonical_Player_decision"]

    resolved=merged.loc[merged["Identity_Status"].eq("Resolved")].copy()
    canonical=consolidate(resolved)
    if not canonical.empty:
        canonical=canonical.sort_values(["Season","Player"],kind="stable")
        canonical.to_csv(OUT,index=False)

    unresolved=merged.loc[merged["Identity_Status"].ne("Resolved")].copy()
    unresolved.to_csv(REVIEW,index=False)

    group=unresolved.groupby(["BRef_Player","BRef_Team","Season","Identity_Status"],
                             dropna=False,sort=True).agg(
        Raw_Rows=("_raw_index","count"),
        Candidate_IDs=("Candidate_IDs",lambda s:";".join(sorted(set(
            x for v in s.fillna("") for x in str(v).split(";") if x
        )))),
        Max_Score=("Top_Score","max"),
        Best_Evidence=("Evidence_Reasons",lambda s:";".join(sorted(set(
            x for v in s.fillna("") for x in str(v).split(";") if x
        )))),
    ).reset_index()
    group.to_csv(GROUPS,index=False)

    vc=dec["Identity_Status"].value_counts()
    audit=pd.DataFrame([{
        "Raw_BRef_Rows":len(raw),
        "Resolved_Rows":int(vc.get("Resolved",0)),
        "Ambiguous_Rows":int(vc.get("Ambiguous",0)),
        "Unmatched_Rows":int(vc.get("Unmatched",0)),
        "Canonical_Player_Seasons":len(canonical),
        "Canonical_Players":canonical["Player_ID"].nunique() if not canonical.empty else 0,
        "Seasons":canonical["Season"].nunique() if not canonical.empty else 0,
        "Same_Team_Year_Resolutions":int((dec["Identity_Method"]=="exact_name_plus_career_year_plus_same_team").sum()),
        "Exact_Name_Resolutions":int((dec["Identity_Method"]=="exact_normalized_name").sum()),
        "Explicit_Alias_Resolutions":int((dec["Identity_Method"]=="explicit_alias").sum()),
        "Review_Groups":len(group),
    }])
    audit.to_csv(AUDIT,index=False)

    print("="*88)
    print("NBA PER-75 — PLAYOFF TEAM/TEMPORAL IDENTITY RESOLVER V1")
    print("="*88)
    print(f"Raw B-Ref rows:             {len(raw):,}")
    print(f"Resolved rows:              {vc.get('Resolved',0):,}")
    print(f"Ambiguous rows:             {vc.get('Ambiguous',0):,}")
    print(f"Unmatched rows:             {vc.get('Unmatched',0):,}")
    print(f"Canonical player-seasons:   {len(canonical):,}")
    print(f"Canonical players:          {canonical['Player_ID'].nunique() if not canonical.empty else 0:,}")
    print(f"Same-team/year resolutions: {int((dec['Identity_Method']=='exact_name_plus_career_year_plus_same_team').sum()):,}")
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
