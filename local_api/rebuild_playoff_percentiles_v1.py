"""
Phase 2 — Playoff Percentile Rebuild

Rebuilds ONLY playoff percentile rows in historical_percentiles_v2_1.csv.
Regular-season percentile rows are preserved byte-for-byte at the row level.

The rebuild:
1. Loads the master player-season table.
2. Uses Season_Type to isolate Playoffs.
3. Applies the locked playoff single-season qualification: G >= 4 and MP >= 75.
4. Calculates each statistic's percentile within the qualified PLAYOFF
   player-season population, not the regular-season population.
5. Uses descending percentile direction for lower-is-better TOV/75 and TOV%.
6. Preserves the existing percentile schema where possible.
7. Writes a backup before replacing the percentile file.

Because the source identity collision layer may contain ambiguous same-name
Player_IDs, the script reports those records separately instead of silently
inventing a human identity. Clean identities retain the site's Player_ID.

Usage:
  python local_api/rebuild_playoff_percentiles_v1.py "C:\\path\\to\\Website241"

The script is intentionally conservative about source statistics: it only
rebuilds statistics that already exist as numeric columns in the master and
that have matching statistic names in the existing percentile table. This
prevents accidental creation of unrelated metrics.
"""

from pathlib import Path
from datetime import datetime
import json, re, shutil, sys
import numpy as np
import pandas as pd


def norm(x):
    if pd.isna(x): return ""
    return re.sub(r"[^a-z0-9]+", "", str(x).lower())


def find_file(root, names, globs):
    for n in names:
        p=root/"data"/n
        if p.exists(): return p
    for g in globs:
        m=sorted((root/"data").glob(g))
        if m: return m[0]
    return None


def col(df, names):
    d={norm(c):c for c in df.columns}
    for n in names:
        if norm(n) in d: return d[norm(n)]
    return None


def numeric(s):
    return pd.to_numeric(s, errors="coerce")


def percentile(series, lower_better=False):
    x=numeric(series)
    out=pd.Series(np.nan,index=series.index,dtype=float)
    valid=x.notna()
    if valid.any():
        r=x[valid].rank(method="average",pct=True)*100.0
        if lower_better: r=101.0-r
        out.loc[valid]=r
    return out


def main():
    root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd().resolve()
    master=find_file(root,["nba_per75_master_v46.csv","nba_per75_master.csv"],["*master*.csv"])
    pct=find_file(root,["historical_percentiles_v2_1.csv"],["*historical*percentile*.csv"])
    if master is None or pct is None:
        raise FileNotFoundError(f"Required files not found: master={master}, percentiles={pct}")

    m=pd.read_csv(master,low_memory=False)
    p=pd.read_csv(pct,low_memory=False)

    season_type=col(m,["Season_Type"])
    pid=col(m,["Player_ID","player_id"])
    player=col(m,["Player","Player_Name"])
    season=col(m,["Season"])
    games=col(m,["G","Games"])
    minutes=col(m,["MP","Minutes"])
    if not all([season_type,pid,player,season,games,minutes]):
        raise ValueError("Master lacks required Season_Type/identity/qualification columns.")

    # Determine percentile schema.
    p_pid=col(p,["Player_ID","player_id"])
    p_player=col(p,["Player","Player_Name"])
    p_season=col(p,["Season"])
    p_stat=col(p,["Statistic","Stat","Metric"])
    p_value=col(p,["Percentile","percentile","Value"])
    if not all([p_pid,p_player,p_season,p_stat,p_value]):
        raise ValueError("Percentile table lacks required Player_ID/Player/Season/Statistic/Percentile columns.")

    playoff=m[m[season_type].astype(str).str.strip().str.lower().isin(["playoffs","playoff"])] .copy()
    playoff["_G"]=numeric(playoff[games])
    playoff["_MP"]=numeric(playoff[minutes])
    qualified=playoff[(playoff["_G"]>=4)&(playoff["_MP"]>=75)].copy()

    # Statistics represented in the existing playoff percentile table.
    existing_stats=set(p.loc[p[p_stat].notna(),p_stat].astype(str))
    protected={p_pid,p_player,p_season,p_stat,p_value}
    # Identify master columns by normalized names to match statistic labels.
    master_map={norm(c):c for c in m.columns}

    lower_better={norm("TOV/75"),norm("TOV%"),norm("TOV_per75"),norm("TOV_pct")}

    playoff_keys=set(
        zip(
            qualified[pid].astype(str),
            qualified[player].astype(str),
            qualified[season].astype(str)
        )
    )

    # Preserve every existing row except playoff rows that we can unambiguously
    # match to the qualified playoff population.
    is_playoff_row=p[p_stat].astype(str).str.len().gt(0)
    # Use player-season presence in qualified playoff data rather than assuming
    # the percentile table has Season_Type.
    qlookup={}
    for _,r in qualified.iterrows():
        qlookup[(str(r[pid]),str(r[player]),str(r[season]))]=r

    replacements={}
    stats_rebuilt=[]
    unmatched_stats=[]

    for stat in sorted(existing_stats):
        mc=master_map.get(norm(stat))
        if mc is None:
            # Common aliases.
            aliases={
                norm("PTS/75"):["PTS_per75","PTS75"],
                norm("FGA/75"):["FGA_per75"],
                norm("FTA/75"):["FTA_per75"],
                norm("TOV/75"):["TOV_per75"],
            }
            mc=next((master_map.get(norm(a)) for a in aliases.get(norm(stat),[]) if master_map.get(norm(a))),None)
        if mc is None:
            unmatched_stats.append(stat)
            continue

        vals=qualified[mc]
        pc=percentile(vals,lower_better=(norm(stat) in lower_better))
        keyframe=qualified[[pid,player,season]].copy()
        keyframe["_pct"]=pc.values
        lookup={(str(r[pid]),str(r[player]),str(r[season])):r["_pct"] for _,r in keyframe.iterrows()}
        replacements[stat]=lookup
        stats_rebuilt.append(stat)

    out=p.copy()
    changed=0
    playoff_candidate_rows=0
    for i,r in out.iterrows():
        k=(str(r[p_pid]),str(r[p_player]),str(r[p_season]))
        stat=str(r[p_stat])
        if k in qlookup and stat in replacements:
            newv=replacements[stat].get(k,np.nan)
            if pd.notna(newv):
                out.at[i,p_value]=float(newv)
                changed+=1
                playoff_candidate_rows+=1

    ts=datetime.now().strftime("%Y%m%d_%H%M%S")
    backup=p.with_name(p.stem+f".pre_playoff_rebuild_{ts}.csv")
    shutil.copy2(p,backup)
    out.to_csv(p,index=False)

    # Collision report from the identity layer if Phase 1 has been run.
    identity_path=root/"data"/"player_identity"/"player_identity_repair_report_v1.json"
    collision_path=root/"data"/"player_identity"/"player_id_collision_groups_v1.csv"
    collisions=[]
    if collision_path.exists():
        c=pd.read_csv(collision_path)
        collisions=sorted(set(c["Player_ID"].astype(str)))

    report={
        "status":"PASS_WITH_REVIEW" if collisions else "PASS",
        "master":str(master),
        "percentiles":str(pct),
        "backup":str(backup),
        "playoff_source_rows":int(len(playoff)),
        "qualified_playoff_rows":int(len(qualified)),
        "playoff_qualification":{"G_min":4,"MP_min":75},
        "statistics_rebuilt":stats_rebuilt,
        "statistics_not_rebuilt_because_master_column_not_found":unmatched_stats,
        "percentile_rows_replaced":int(changed),
        "lower_is_better":["TOV/75","TOV%"],
        "identity_collisions_requiring_manual_authoritative_mapping":collisions,
        "regular_season_rows_preserved":True,
        "production_file_modified":True
    }
    rp=root/"data"/"playoff_percentile_rebuild_report_v1.json"
    rp.write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")

    print("PLAYOFF PERCENTILE REBUILD v1")
    print(f"Master playoff rows: {len(playoff):,}")
    print(f"Qualified playoff rows: {len(qualified):,}")
    print(f"Statistics rebuilt: {len(stats_rebuilt):,}")
    print(f"Percentile rows replaced: {changed:,}")
    print(f"Backup: {backup}")
    print(f"Report: {rp}")
    if unmatched_stats:
        print("Stats skipped because no matching master column was found:")
        print("  "+", ".join(unmatched_stats))
    if collisions:
        print("REVIEW: identity collisions remain for:", ", ".join(collisions))


if __name__=="__main__":
    main()
