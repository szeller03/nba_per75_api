r"""
NBA PER-75 — BASKETBALL-REFERENCE PLAYOFF IDENTITY INTEGRATION V1

Input:
  C:\Users\szell\OneDrive\Desktop\NBA_Per75\data\nba_per75_playoffs_bref_v1.csv
  C:\Users\szell\OneDrive\Desktop\NBA_Per75\player_website_identity_v1\website_player_identity_v1.csv
  C:\Users\szell\OneDrive\Desktop\NBA_Per75\data\nba_per75_master_dreb_v2.csv

Output:
  data\nba_per75_playoffs_player_season_v1.csv
  data\nba_per75_playoffs_identity_audit_v1.csv
  data\nba_per75_playoffs_unmatched_v1.csv

This layer:
  1. resolves B-Ref player names to the site's canonical 4,896-player IDs;
  2. uses deterministic normalized-name matching first;
  3. uses career-season overlap only when exactly one canonical player can be
     established from the site's season universe;
  4. consolidates multiple B-Ref team rows into one player-season row;
  5. never fuzzy-guesses an identity;
  6. preserves unresolved rows for manual review.

It does not calculate PER-75 or percentiles.
"""

from __future__ import annotations
import argparse
import re
import unicodedata
from pathlib import Path
import pandas as pd

ROOT=Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75")
RAW=ROOT/"data"/"nba_per75_playoffs_bref_v1.csv"
IDENTITY=ROOT/"player_website_identity_v1"/"website_player_identity_v1.csv"
MASTER=ROOT/"data"/"nba_per75_master_dreb_v2.csv"

OUT=ROOT/"data"/"nba_per75_playoffs_player_season_v1.csv"
AUDIT=ROOT/"data"/"nba_per75_playoffs_identity_audit_v1.csv"
UNMATCHED=ROOT/"data"/"nba_per75_playoffs_unmatched_v1.csv"

ADDITIVE=["G","GS","MP","FG","FGA","3P","3PA","2P","2PA","FT","FTA",
          "ORB","DRB","TRB","AST","STL","BLK","TOV","PF","PTS"]

PCT_DENOMS={
    "FG%":"FGA","3P%":"3PA","2P%":"2PA","FT%":"FTA","eFG%":"FGA"
}

ALIASES={
    # Conservative known B-Ref/name variants can be added here. Keys and
    # values are normalized through norm_name before matching.
}

def norm_name(value):
    s="" if pd.isna(value) else str(value)
    s=unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode("ascii")
    s=s.casefold().replace("’","'").replace("`","'")
    s=re.sub(r"[\*\u2020\u2021]+","",s)
    s=s.replace("&"," and ")
    s=re.sub(r"[^a-z0-9 ]+"," ",s)
    s=re.sub(r"\b(jr|sr|ii|iii|iv|v)\b","",s)
    s=re.sub(r"\s+"," ",s).strip()
    return s

def season_year(value):
    if pd.isna(value): return None
    s=str(value).strip()
    m=re.match(r"^(\d{4})",s)
    return int(m.group(1)) if m else None

def season_set(value):
    if pd.isna(value): return set()
    s=str(value)
    return {season_year(x) for x in re.split(r"[;,|]+",s) if season_year(x) is not None}

def find_col(df,names):
    norm={re.sub(r"[^a-z0-9]","",str(c).casefold()):c for c in df.columns}
    for n in names:
        k=re.sub(r"[^a-z0-9]","",n.casefold())
        if k in norm:return norm[k]
    return None

def clean_numeric(v):
    if pd.isna(v): return None
    try: return float(v)
    except: return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--raw",default=str(RAW))
    ap.add_argument("--identity",default=str(IDENTITY))
    ap.add_argument("--master",default=str(MASTER))
    args=ap.parse_args()

    raw=pd.read_csv(args.raw,low_memory=False)
    ident=pd.read_csv(args.identity,low_memory=False)
    master=pd.read_csv(args.master,low_memory=False)

    rid=find_col(raw,["Player","Player_Name"])
    rseason=find_col(raw,["Season"])
    rteam=find_col(raw,["Team","Tm"])
    iid=find_col(ident,["Player_ID","PlayerId","PlayerID","player_id"])
    iname=find_col(ident,["Player","Player_Name","Display_Name","Name"])
    mid=find_col(master,["Player_ID","PlayerId","PlayerID","player_id"])
    mname=find_col(master,["Player","Player_Name","Display_Name","Name"])
    mseason=find_col(master,["Season","season"])

    if not rid or not rseason or not iid or not iname:
        raise ValueError("Required player/name/season columns are missing.")

    ident=ident.copy()
    ident["_norm_name"]=ident[iname].map(norm_name)
    ident["_pid"]=ident[iid].astype(str).str.strip()

    # Canonical identity lookup. Multiple players sharing a normalized name
    # remain ambiguous until career-year overlap can deterministically resolve.
    name_to_ids={}
    for _,r in ident.iterrows():
        name_to_ids.setdefault(r["_norm_name"],set()).add(r["_pid"])

    # Canonical season universe for overlap disambiguation.
    careers={}
    if mid and mname and mseason:
        for _,r in master[[mid,mname,mseason]].dropna(subset=[mname]).iterrows():
            pid=str(r[mid]).strip()
            yr=season_year(r[mseason])
            if yr is not None:
                careers.setdefault(pid,set()).add(yr)

    # Identity display names.
    display={}
    for _,r in ident.iterrows():
        display[str(r["_pid"])]=str(r[iname])

    decisions=[]
    unmatched=[]

    for idx,r in raw.iterrows():
        source_name=str(r[rid]).strip()
        n=norm_name(source_name)
        year=season_year(r[rseason])
        candidates=set(name_to_ids.get(n,set()))
        method="exact_normalized_name"

        # Conservative alias path.
        if not candidates and n in {norm_name(k):v for k,v in ALIASES.items()}:
            alias=ALIASES[next(k for k in ALIASES if norm_name(k)==n)]
            candidates=set(name_to_ids.get(norm_name(alias),set()))
            method="explicit_alias"

        # Career overlap only if it leaves exactly one candidate.
        if len(candidates)>1 and year is not None:
            overlapping=[pid for pid in candidates if year in careers.get(pid,set())]
            if len(overlapping)==1:
                candidates={overlapping[0]}
                method="exact_name_plus_career_year"

        if len(candidates)==1:
            pid=next(iter(candidates))
            decisions.append({
                "raw_index":idx,
                "Player_ID":pid,
                "Canonical_Player":display.get(pid,source_name),
                "BRef_Player":source_name,
                "Season":year,
                "Identity_Status":"Resolved",
                "Identity_Method":method,
            })
        else:
            status="Unmatched" if len(candidates)==0 else "Ambiguous"
            decisions.append({
                "raw_index":idx,
                "Player_ID":None,
                "Canonical_Player":None,
                "BRef_Player":source_name,
                "Season":year,
                "Identity_Status":status,
                "Identity_Method":method if candidates else "No deterministic match",
                "Candidate_IDs":";".join(sorted(candidates)),
            })
            unmatched.append(idx)

    dec=pd.DataFrame(decisions)
    raw2=raw.copy()
    raw2["_raw_index"]=range(len(raw2))
    merged=raw2.merge(
        dec,
        left_on="_raw_index",
        right_on="raw_index",
        how="left",
        validate="one_to_one",
        suffixes=("_raw", "_identity"),
    )

    # The raw B-Ref file intentionally carries a blank Player_ID placeholder,
    # while the identity decision carries the canonical NBA Player_ID. Pandas
    # therefore creates Player_ID_raw / Player_ID_identity on merge. Normalize
    # those fields explicitly before consolidation instead of relying on a
    # column name that may not exist after the merge.
    if "Player_ID_identity" in merged.columns:
        merged["Player_ID"] = merged["Player_ID_identity"]
    elif "Player_ID" not in merged.columns:
        raise KeyError("Canonical Player_ID was not produced by identity resolution.")

    if "Season_identity" in merged.columns:
        merged["Season"] = merged["Season_identity"]
    elif "Season" not in merged.columns:
        raise KeyError("Canonical Season was not produced by identity resolution.")

    resolved=merged.loc[merged["Identity_Status"].eq("Resolved")].copy()

    # Consolidate multiple B-Ref team rows into one canonical player-season.
    # Additive totals are summed. Percentages are recalculated from summed
    # attempts/free throws rather than averaged.
    rows=[]
    for (pid,year),g in resolved.groupby(["Player_ID","Season"],dropna=False,sort=True):
        out={
            "Player_ID":str(pid),
            "Player":g["Canonical_Player"].iloc[0],
            "Season":int(year),
            "Season_Type":"Playoffs",
            "Teams":" / ".join(sorted({str(x) for x in g.get(rteam,pd.Series(dtype=str)).dropna().tolist()})),
            "BRef_Rows_Combined":int(len(g)),
        }
        for c in ADDITIVE:
            if c in g.columns:
                vals=pd.to_numeric(g[c],errors="coerce")
                out[c]=float(vals.sum(min_count=1)) if vals.notna().any() else None

        # Recalculate shooting percentages from consolidated totals.
        for pct,den in PCT_DENOMS.items():
            num=None
            if pct=="FG%": num="FG"
            elif pct=="3P%": num="3P"
            elif pct=="2P%": num="2P"
            elif pct=="FT%": num="FT"
            elif pct=="eFG%":
                if out.get("FGA") is not None:
                    fg=out.get("FG")
                    three=out.get("3P")
                    out[pct]=((fg+0.5*three)/out["FGA"]) if fg is not None and three is not None and out["FGA"] else None
                    continue
            if num and out.get(den) not in (None,0) and out.get(num) is not None:
                out[pct]=out[num]/out[den]
            else:
                out[pct]=None

        rows.append(out)

    canonical=pd.DataFrame(rows)
    canonical_cols=["Player_ID","Player","Season","Season_Type","Teams","BRef_Rows_Combined"]+[
        c for c in ADDITIVE+list(PCT_DENOMS) if c in canonical.columns
    ]
    canonical=canonical[canonical_cols].sort_values(["Season","Player"],kind="stable")

    # Audit.
    status_counts=dec["Identity_Status"].value_counts().to_dict()
    audit=pd.DataFrame([{
        "Raw_BRef_Rows":len(raw),
        "Resolved_Rows":int(status_counts.get("Resolved",0)),
        "Ambiguous_Rows":int(status_counts.get("Ambiguous",0)),
        "Unmatched_Rows":int(status_counts.get("Unmatched",0)),
        "Canonical_Player_Seasons":len(canonical),
        "Canonical_Players":canonical["Player_ID"].nunique() if not canonical.empty else 0,
        "Seasons":canonical["Season"].nunique() if not canonical.empty else 0,
        "First_Season":canonical["Season"].min() if not canonical.empty else None,
        "Last_Season":canonical["Season"].max() if not canonical.empty else None,
        "Identity_Method_Exact":int((dec["Identity_Method"]=="exact_normalized_name").sum()),
        "Identity_Method_Alias":int((dec["Identity_Method"]=="explicit_alias").sum()),
        "Identity_Method_Career_Overlap":int((dec["Identity_Method"]=="exact_name_plus_career_year").sum()),
    }])

    unresolved=merged.loc[merged["Identity_Status"].ne("Resolved")].copy()

    OUT.parent.mkdir(parents=True,exist_ok=True)
    canonical.to_csv(OUT,index=False)
    audit.to_csv(AUDIT,index=False)
    unresolved.to_csv(UNMATCHED,index=False)

    print("="*88)
    print("NBA PER-75 — BASKETBALL-REFERENCE PLAYOFF IDENTITY INTEGRATION V1")
    print("="*88)
    print(f"Raw B-Ref rows:             {len(raw):,}")
    print(f"Resolved rows:              {status_counts.get('Resolved',0):,}")
    print(f"Ambiguous rows:             {status_counts.get('Ambiguous',0):,}")
    print(f"Unmatched rows:             {status_counts.get('Unmatched',0):,}")
    print(f"Canonical player-seasons:   {len(canonical):,}")
    print(f"Canonical players:           {canonical['Player_ID'].nunique() if not canonical.empty else 0:,}")
    print(f"Seasons:                     {canonical['Season'].nunique() if not canonical.empty else 0}")
    print(f"Output:                      {OUT}")
    print(f"Audit:                       {AUDIT}")
    print(f"Unresolved review:           {UNMATCHED}")
    if len(unresolved):
        print()
        print("IMPORTANT: unresolved identities are retained for review and are NOT guessed.")
    else:
        print()
        print("IDENTITY INTEGRATION: COMPLETE — no unresolved B-Ref rows.")

if __name__=="__main__":
    main()
