r"""
NBA PER-75 — Player Profile Data Integrity Forensic Audit v4.1

READ ONLY. Produces:
  data/player_profile_data_integrity_forensic_report_v4.json
  data/player_profile_data_integrity_forensic_duplicates_v4.csv

Run by passing the Website241 root directory as the first argument.
"""

from __future__ import annotations
import argparse, json, re
from pathlib import Path
import pandas as pd

FILES = {
    "master": "nba_per75_master_v46.csv",
    "career_sdi": "regular_career_sdi_v4_wowy_rts.csv",
    "regular_sdi": "regular_sdi_v4_wowy_player_seasons.csv",
    "playoff_sdi": "playoff_sdi_v4_player_seasons.csv",
    "wowy": "player_wowy_statistics_v1.csv",
    "percentiles": "player_season_percentiles_long_v2_1.csv",
    "regular_peak": "regular_profile_peaks_wowy_rts_v3_career_sdi.json",
    "playoff_peak": "playoff_profile_peaks_authoritative_v9.json",
}

def locate(root, filename):
    for base in [root/"data", root/"local_api"/"cache", root]:
        p = base/filename
        if p.exists():
            return p
    m = list(root.rglob(filename))
    return m[0] if m else None

def norm(x):
    return re.sub(r"[^a-z0-9]+", "_", str(x).lower()).strip("_")

def pcol(df):
    for x in ["Player","Player_Name","player_name","Name"]:
        for c in df.columns:
            if norm(c)==norm(x): return c
    return None

def idcol(df):
    for x in ["Player_ID","PlayerId","PlayerID","player_id"]:
        for c in df.columns:
            if norm(c)==norm(x): return c
    return None

def scol(df):
    for x in ["Season","SeasonEndYear","Season_End_Year","Year"]:
        for c in df.columns:
            if norm(c)==norm(x): return c
    return None

def stcol(df):
    for x in ["Season_Type","SeasonType"]:
        for c in df.columns:
            if norm(c)==norm(x): return c
    return None

def teamcols(df):
    return [c for c in df.columns if any(k in norm(c) for k in
        ["team","tm","franchise","team_id","teamid"])]

def read_csv(p):
    return pd.read_csv(p, low_memory=False) if p else None

def clean_player(x):
    return str(x).replace("*","").strip().casefold()

def duplicate_groups(df, keys):
    if df is None or not all(c in df.columns for c in keys):
        return []
    d = df[df.duplicated(keys, keep=False)].copy()
    if d.empty: return []
    return d.sort_values(keys).to_dict("records")

def wilt_rows(df):
    if df is None or not pcol(df): return []
    p=pcol(df); s=scol(df)
    r=df[df[p].map(clean_player).eq("wilt chamberlain")].copy()
    pts=[c for c in df.columns if "pts" in norm(c) and "per75" in norm(c)]
    keep=[c for c in [idcol(df),p,s,stcol(df)] if c] + pts + teamcols(df)
    keep=list(dict.fromkeys([c for c in keep if c in df.columns]))
    return r[keep].to_dict("records")

def find_peak_payload(p):
    if not p: return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e: return {"read_error":str(e)}

def peak_records(payload):
    if isinstance(payload,dict):
        x=payload.get("players")
        return x if isinstance(x,list) else []
    return payload if isinstance(payload,list) else []

def season_year(x):
    m=re.search(r"(19|20)\d{2}",str(x))
    return int(m.group()) if m else None

def peak_checks(payload):
    rows=peak_records(payload); out=[]
    for r in rows:
        seasons=r.get("peak_seasons") or []
        years=[season_year(x) for x in seasons]
        years=[x for x in years if x is not None]
        span=(max(years)-min(years)+1) if years else None
        gaps=[]
        if years:
            ys=sorted(set(years))
            gaps=[b-a for a,b in zip(ys,ys[1:]) if b-a>1]
        out.append({
            "player_id":r.get("Player_ID",r.get("player_id")),
            "player":r.get("Player",r.get("player_name")),
            "season_count":len(seasons),
            "seasons":seasons,
            "calendar_span":span,
            "gaps":gaps,
            "five_seasons":len(seasons)==5,
            "max_six_span":span is not None and span<=6,
            "no_two_year_gap":all(g<=2 for g in gaps),
        })
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("website_root")
    args=ap.parse_args()
    root=Path(args.website_root).expanduser().resolve()
    if not root.exists(): raise SystemExit(f"Missing root: {root}")

    paths={k:locate(root,v) for k,v in FILES.items()}
    tables={k:read_csv(paths[k]) for k in FILES if paths[k] and paths[k].suffix.lower()==".csv"}

    report={
        "phase":"Player Profile Data Integrity Forensic Audit v4",
        "read_only":True,
        "sources":{k:str(v) if v else None for k,v in paths.items()},
        "schemas":{},
        "master_forensics":{},
        "playoff_sdi_forensics":{},
        "wilt_cross_section":{},
        "peak_methodology_checks":{},
        "wowY_flow_checks":{},
        "followups":[
            "Resolve every Master duplicate under Player_ID + Season + Season_Type using the full rows.",
            "Resolve every Playoff SDI duplicate under Player_ID + SeasonEndYear using the full six-column rows.",
            "Determine the canonical Wilt regular-season row before comparing Profile vs Compare.",
            "Verify five-season regular peak selections and <=6-calendar-year span for all records.",
            "Verify five-season playoff peak selections and their locked qualification rule.",
            "Trace WOWY raw values into Career SDI and Peak SDI without changing Route A SDI.",
        ]
    }

    for k,df in tables.items():
        report["schemas"][k]={
            "rows":len(df),
            "columns":list(df.columns),
            "column_count":len(df.columns),
            "player_column":pcol(df),
            "player_id_column":idcol(df),
            "season_column":scol(df),
            "season_type_column":stcol(df),
            "team_like_columns":teamcols(df),
        }

    master=tables.get("master")
    if master is not None:
        keys=[c for c in [idcol(master),scol(master),stcol(master)] if c]
        rows=duplicate_groups(master,keys)
        # Collapse to unique groups and preserve every full row.
        if rows:
            g=master[master.duplicated(keys,keep=False)].copy()
            groups=[]
            for vals,sub in g.groupby(keys,dropna=False,sort=True):
                groups.append({
                    "identity":dict(zip(keys, vals if isinstance(vals,tuple) else [vals])),
                    "row_count":len(sub),
                    "full_rows":sub.to_dict("records")
                })
            report["master_forensics"]={
                "identity_key":keys,
                "duplicate_group_count":len(groups),
                "duplicate_row_count":len(g),
                "groups":groups
            }
        else:
            report["master_forensics"]={"identity_key":keys,"duplicate_group_count":0,"duplicate_row_count":0,"groups":[]}
        report["wilt_cross_section"]["master"]=wilt_rows(master)

    playoff=tables.get("playoff_sdi")
    if playoff is not None:
        keys=[c for c in [idcol(playoff),scol(playoff)] if c]
        d=playoff[playoff.duplicated(keys,keep=False)].copy()
        groups=[]
        if not d.empty:
            for vals,sub in d.groupby(keys,dropna=False,sort=True):
                groups.append({
                    "identity":dict(zip(keys, vals if isinstance(vals,tuple) else [vals])),
                    "row_count":len(sub),
                    "full_rows":sub.to_dict("records")
                })
        report["playoff_sdi_forensics"]={
            "identity_key":keys,
            "duplicate_group_count":len(groups),
            "duplicate_row_count":len(d),
            "groups":groups
        }

    for k,df in tables.items():
        report["wilt_cross_section"][k]=wilt_rows(df)

    for k in ["regular_peak","playoff_peak"]:
        payload=find_peak_payload(paths[k])
        checks=peak_checks(payload)
        report["peak_methodology_checks"][k]={
            "record_count":len(checks),
            "invalid_five_season_count":sum(not x["five_seasons"] for x in checks),
            "invalid_span_count":sum(not x["max_six_span"] for x in checks),
            "invalid_gap_count":sum(not x["no_two_year_gap"] for x in checks),
            "examples":[x for x in checks if not (x["five_seasons"] and x["max_six_span"] and x["no_two_year_gap"])][:25],
            "sample_valid_records":[x for x in checks if x["five_seasons"] and x["max_six_span"] and x["no_two_year_gap"]][:10]
        }

    # WOWY flow: report available raw columns and matching player/season rows.
    w=tables.get("wowy"); c=tables.get("career_sdi"); r=tables.get("regular_sdi")
    wcols=[x for x in (w.columns if w is not None else []) if "wowy" in norm(x)]
    report["wowY_flow_checks"]={
        "wowy_columns":[x for x in (w.columns if w is not None else [])],
        "wowy_value_columns":wcols,
        "career_sdi_wowy_columns":[x for x in (c.columns if c is not None else []) if "wowy" in norm(x)],
        "regular_sdi_wowy_columns":[x for x in (r.columns if r is not None else []) if "wowy" in norm(x)],
    }

    out=root/"data"/"player_profile_data_integrity_forensic_report_v4.json"
    out.write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")

    # Also produce a flat CSV containing every forensic duplicate row.
    flat=[]
    for dataset,section in [("master",report["master_forensics"]),("playoff_sdi",report["playoff_sdi_forensics"])]:
        for gi,g in enumerate(section.get("groups",[]),1):
            for row in g["full_rows"]:
                x={"dataset":dataset,"duplicate_group":gi,**{f"identity_{k}":v for k,v in g["identity"].items()},**row}
                flat.append(x)
    dupout=root/"data"/"player_profile_data_integrity_forensic_duplicates_v4.csv"
    pd.DataFrame(flat).to_csv(dupout,index=False)

    print("="*90)
    print("PLAYER PROFILE DATA INTEGRITY FORENSIC AUDIT v4")
    print("="*90)
    print("MASTER DUPLICATES:",report["master_forensics"].get("duplicate_group_count"),"groups /",
          report["master_forensics"].get("duplicate_row_count"),"rows")
    for g in report["master_forensics"].get("groups",[]):
        print("\nMASTER GROUP:",g["identity"],"rows=",g["row_count"])
        for row in g["full_rows"]:
            print(row)
    print("\nPLAYOFF SDI DUPLICATES:",report["playoff_sdi_forensics"].get("duplicate_group_count"),"groups /",
          report["playoff_sdi_forensics"].get("duplicate_row_count"),"rows")
    for g in report["playoff_sdi_forensics"].get("groups",[]):
        print("\nPLAYOFF GROUP:",g["identity"],"rows=",g["row_count"])
        for row in g["full_rows"]:
            print(row)
    print("\nPEAK CHECKS")
    for k,v in report["peak_methodology_checks"].items():
        print(k,v)
    print("\nWILT")
    print(json.dumps(report["wilt_cross_section"],indent=2,default=str))
    print("\nWOWY FLOW")
    print(json.dumps(report["wowY_flow_checks"],indent=2))
    print("\nJSON REPORT:",out)
    print("DUPLICATE CSV:",dupout)

if __name__=="__main__":
    main()
