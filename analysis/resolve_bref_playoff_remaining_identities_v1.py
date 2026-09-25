"""
NBA PER-75 — BASKETBALL-REFERENCE PLAYOFF REMAINING IDENTITY RESOLVER V1

Purpose:
    Review the unresolved B-Ref playoff identities produced by
    integrate_bref_playoff_identity_v1.py.

Safety:
    - Exact normalized names only.
    - Explicit aliases only.
    - Career-year overlap only when exactly one candidate remains.
    - Never fuzzy-match.
    - Never silently guess.
    - Does not modify the regular-season master.

It can automatically resolve only deterministic cases that were not already
resolved by V22.1, then rebuild the canonical playoff player-season file.

Inputs:
    NBA_Per75/data/nba_per75_playoffs_bref_v1.csv
    NBA_Per75/data/nba_per75_playoffs_unmatched_v1.csv
    NBA_Per75/player_website_identity_v1/website_player_identity_v1.csv
    NBA_Per75/data/nba_per75_master_dreb_v2.csv

Outputs:
    NBA_Per75/data/nba_per75_playoffs_player_season_v2.csv
    NBA_Per75/data/nba_per75_playoffs_identity_audit_v2.csv
    NBA_Per75/data/nba_per75_playoffs_unresolved_review_v2.csv
    NBA_Per75/data/nba_per75_playoffs_identity_candidate_groups_v1.csv
"""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata
import pandas as pd

ROOT = Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75")
RAW = ROOT/"data"/"nba_per75_playoffs_bref_v1.csv"
OLD_UNRESOLVED = ROOT/"data"/"nba_per75_playoffs_unmatched_v1.csv"
IDENTITY = ROOT/"player_website_identity_v1"/"website_player_identity_v1.csv"
MASTER = ROOT/"data"/"nba_per75_master_dreb_v2.csv"

OUT = ROOT/"data"/"nba_per75_playoffs_player_season_v2.csv"
AUDIT = ROOT/"data"/"nba_per75_playoffs_identity_audit_v2.csv"
REVIEW = ROOT/"data"/"nba_per75_playoffs_unresolved_review_v2.csv"
GROUPS = ROOT/"data"/"nba_per75_playoffs_identity_candidate_groups_v1.csv"

ALIASES = {
    # Add only verified exact aliases here. Do not add speculative aliases.
}

ADDITIVE = [
    "G","GS","MP","FG","FGA","3P","3PA","2P","2PA",
    "FT","FTA","ORB","DRB","TRB","AST","STL","BLK","TOV","PF","PTS"
]

def norm_name(x):
    s=unicodedata.normalize("NFKD", str(x)).encode("ascii","ignore").decode("ascii")
    s=s.casefold()
    s=re.sub(r"[^a-z0-9]+"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def season_year(x):
    s=str(x).strip()
    m=re.search(r"(19|20)\d{2}",s)
    return int(m.group(0)) if m else None

def find_col(df, names):
    lower={str(c).casefold():c for c in df.columns}
    for n in names:
        if n.casefold() in lower:
            return lower[n.casefold()]
    return None

def load_identity():
    ids=pd.read_csv(IDENTITY,low_memory=False)
    pid=find_col(ids,["Player_ID","player_id","NBA_Player_ID"])
    name=find_col(ids,["Player","Display_Name","Player_Name","Name"])
    seasons=find_col(ids,["Available_Seasons"])
    first=find_col(ids,["First_Season"])
    last=find_col(ids,["Last_Season"])
    if not pid or not name:
        raise KeyError("Identity file must contain Player_ID and Player/Display_Name.")

    display={}
    names={}
    careers={}

    for _,r in ids.iterrows():
        p=str(r[pid]).strip()
        if not p or p.casefold()=="nan": continue
        n=norm_name(r[name])
        if n:
            names.setdefault(n,set()).add(p)
        display[p]=str(r[name]).strip()

        yrs=set()
        if seasons and pd.notna(r[seasons]):
            for token in re.findall(r"(?:19|20)\d{2}",str(r[seasons])):
                yrs.add(int(token))
        if first and pd.notna(r[first]) and last and pd.notna(r[last]):
            try:
                a=int(float(r[first])); b=int(float(r[last]))
                yrs.update(range(a,b+1))
            except Exception:
                pass
        careers[p]=yrs

    return names,display,careers

def canonicalize(raw, names, display, careers):
    decisions=[]
    alias_map={norm_name(k):norm_name(v) for k,v in ALIASES.items()}

    for idx,r in raw.iterrows():
        source=str(r.get("Player","")).strip()
        year=season_year(r.get("Season"))
        n=norm_name(source)
        candidates=set(names.get(n,set()))
        method="exact_normalized_name"

        if not candidates and n in alias_map:
            candidates=set(names.get(alias_map[n],set()))
            method="explicit_alias"

        if len(candidates)>1 and year is not None:
            overlap=[p for p in candidates if year in careers.get(p,set())]
            if len(overlap)==1:
                candidates={overlap[0]}
                method="exact_name_plus_career_year"

        if len(candidates)==1:
            pid=next(iter(candidates))
            decisions.append({
                "raw_index":idx,
                "Player_ID":pid,
                "Canonical_Player":display.get(pid,source),
                "BRef_Player":source,
                "Season":year,
                "Identity_Status":"Resolved",
                "Identity_Method":method,
                "Candidate_IDs":";".join(sorted(candidates)),
            })
        else:
            status="Ambiguous" if candidates else "Unmatched"
            overlap=[p for p in candidates if year is not None and year in careers.get(p,set())]
            decisions.append({
                "raw_index":idx,
                "Player_ID":None,
                "Canonical_Player":None,
                "BRef_Player":source,
                "Season":year,
                "Identity_Status":status,
                "Identity_Method":method if candidates else "No deterministic match",
                "Candidate_IDs":";".join(sorted(candidates)),
                "Career_Overlap_IDs":";".join(sorted(overlap)),
                "Candidate_Count":len(candidates),
            })
    return pd.DataFrame(decisions)

def consolidate(merged):
    resolved=merged.loc[merged["Identity_Status"].eq("Resolved")].copy()
    if resolved.empty:
        return pd.DataFrame()

    rows=[]
    for (pid,year),g in resolved.groupby(["Player_ID","Season"],dropna=False,sort=True):
        teams=[]
        if "Team" in g.columns:
            teams=[str(x) for x in g["Team"].dropna().tolist() if str(x).strip()]
        out={
            "Player_ID":str(pid),
            "Player":str(g["Canonical_Player"].iloc[0]),
            "Season":int(year),
            "Season_Type":"Playoffs",
            "Teams":" / ".join(sorted(set(teams))),
            "BRef_Rows_Combined":int(len(g)),
        }
        for c in ADDITIVE:
            if c in g.columns:
                v=pd.to_numeric(g[c],errors="coerce")
                out[c]=float(v.sum(min_count=1)) if v.notna().any() else None

        for pct,num,den in [
            ("FG%","FG","FGA"),("3P%","3P","3PA"),("2P%","2P","2PA"),
            ("FT%","FT","FTA")
        ]:
            a=out.get(num); b=out.get(den)
            out[pct]=a/b if a is not None and b not in (None,0) else None

        fg=out.get("FG"); three=out.get("3P"); fga=out.get("FGA")
        out["eFG%"]=(fg+0.5*three)/fga if fg is not None and three is not None and fga not in (None,0) else None
        rows.append(out)

    return pd.DataFrame(rows)

def main():
    raw=pd.read_csv(RAW,low_memory=False)
    names,display,careers=load_identity()
    dec=canonicalize(raw,names,display,careers)

    raw2=raw.copy()
    raw2["_raw_index"]=range(len(raw2))
    merged=raw2.merge(
        dec,left_on="_raw_index",right_on="raw_index",
        how="left",validate="one_to_one",suffixes=("_raw","_identity")
    )
    if "Player_ID_identity" in merged.columns:
        merged["Player_ID"]=merged["Player_ID_identity"]
    if "Season_identity" in merged.columns:
        merged["Season"]=merged["Season_identity"]

    canonical=consolidate(merged)
    if not canonical.empty:
        canonical=canonical.sort_values(["Season","Player"],kind="stable")
        canonical.to_csv(OUT,index=False)

    unresolved=merged.loc[merged["Identity_Status"].ne("Resolved")].copy()
    unresolved.to_csv(REVIEW,index=False)

    # Candidate-group review makes the remaining ambiguity understandable:
    # one row per B-Ref name + season with all candidate IDs and career overlap.
    group_cols=["BRef_Player","Season","Identity_Status"]
    group=unresolved.groupby(group_cols,dropna=False,sort=True).agg(
        Raw_Rows=("raw_index","count"),
        Candidate_IDs=("Candidate_IDs",lambda s:";".join(sorted(set(
            x for v in s.fillna("") for x in str(v).split(";") if x
        )))),
        Career_Overlap_IDs=("Career_Overlap_IDs",lambda s:";".join(sorted(set(
            x for v in s.fillna("") for x in str(v).split(";") if x
        )))),
    ).reset_index()
    group["Candidate_Count"]=group["Candidate_IDs"].map(
        lambda s: len([x for x in str(s).split(";") if x])
    )
    group.to_csv(GROUPS,index=False)

    counts=dec["Identity_Status"].value_counts()
    audit=pd.DataFrame([{
        "Raw_BRef_Rows":len(raw),
        "Resolved_Rows":int(counts.get("Resolved",0)),
        "Ambiguous_Rows":int(counts.get("Ambiguous",0)),
        "Unmatched_Rows":int(counts.get("Unmatched",0)),
        "Canonical_Player_Seasons":len(canonical),
        "Canonical_Players":canonical["Player_ID"].nunique() if not canonical.empty else 0,
        "Seasons":canonical["Season"].nunique() if not canonical.empty else 0,
        "First_Season":canonical["Season"].min() if not canonical.empty else None,
        "Last_Season":canonical["Season"].max() if not canonical.empty else None,
        "Review_Groups":len(group),
        "Exact_Name_Resolutions":int((dec["Identity_Method"]=="exact_normalized_name").sum()),
        "Explicit_Alias_Resolutions":int((dec["Identity_Method"]=="explicit_alias").sum()),
        "Career_Overlap_Resolutions":int((dec["Identity_Method"]=="exact_name_plus_career_year").sum()),
    }])
    audit.to_csv(AUDIT,index=False)

    print("="*88)
    print("NBA PER-75 — BASKETBALL-REFERENCE PLAYOFF REMAINING IDENTITY REVIEW V1")
    print("="*88)
    print(f"Raw B-Ref rows:             {len(raw):,}")
    print(f"Resolved rows:              {counts.get('Resolved',0):,}")
    print(f"Ambiguous rows:             {counts.get('Ambiguous',0):,}")
    print(f"Unmatched rows:             {counts.get('Unmatched',0):,}")
    print(f"Canonical player-seasons:   {len(canonical):,}")
    print(f"Canonical players:          {canonical['Player_ID'].nunique() if not canonical.empty else 0:,}")
    print(f"Review groups:              {len(group):,}")
    print(f"Canonical output:           {OUT}")
    print(f"Identity audit:             {AUDIT}")
    print(f"Unresolved review:          {REVIEW}")
    print(f"Candidate groups:           {GROUPS}")
    print()
    print("No fuzzy identity assignment was performed.")
    print("No identity was silently guessed.")

if __name__=="__main__":
    main()
