"""
NBA PER-75 — PLAYOFF 46-STAT PERCENTILE LAYER V1

Consumes the finalized playoff 46-stat layer produced by V37.

Inputs:
  data/nba_per75_playoff_46_stats_v1/nba_per75_playoffs_46_stats_v1.csv
  data/nba_per75_playoff_46_stats_v1/nba_per75_playoffs_career_46_stats_v1.csv
  data/nba_per75_playoff_46_stats_v1/playoff_46_stat_registry_v1.csv

Outputs:
  Season percentiles: Season / Era / Historical
  Career percentiles: Career
  All 46 registry statistics are retained in the registry and output schema.
  Unsupported statistics remain missing and receive no percentile.

Qualification:
  Season: G >= 7 AND MP >= 125
  Career: G >= 50 AND MP >= 1500

Non-qualified records remain present with statistics intact; only percentile
values are withheld.
"""

from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75")
DATA=ROOT/"data"/"nba_per75_playoff_46_stats_v1"
OUT=DATA/"percentiles_v1"
SEASON=DATA/"nba_per75_playoffs_46_stats_v1.csv"
CAREER=DATA/"nba_per75_playoffs_career_46_stats_v1.csv"
REG=DATA/"playoff_46_stat_registry_v1.csv"

SEASON_MIN_G=7
SEASON_MIN_MP=125
CAREER_MIN_G=50
CAREER_MIN_MP=1500

ERA_BANDS=[
    ("1951-52_to_1969-70",1952,1970),
    ("1970-71_to_1979-80",1971,1980),
    ("1980-81_to_1989-90",1981,1990),
    ("1990-91_to_1999-00",1991,2000),
    ("2000-01_to_2009-10",2001,2010),
    ("2010-11_to_2019-20",2011,2020),
    ("2020-21_to_2025-26",2021,2026),
]

LOWER_IS_BETTER={
    "TOV_pct","PF_per75","TOV_per75"
}

def pct(s,higher=True):
    x=pd.to_numeric(s,errors="coerce")
    valid=x.notna()
    out=pd.Series(np.nan,index=s.index,dtype=float)
    n=int(valid.sum())
    if n==0: return out
    if n==1:
        out.loc[valid]=100.0
        return out
    ranks=x.loc[valid].rank(method="average",ascending=not higher)
    out.loc[valid]=100.0*(n-ranks)/(n-1)
    return out

def era(y):
    try: y=int(y)
    except: return "UNRESOLVED"
    for label,a,b in ERA_BANDS:
        if a<=y<=b: return label
    return "UNRESOLVED"

def main():
    OUT.mkdir(parents=True,exist_ok=True)

    season=pd.read_csv(SEASON,low_memory=False)
    career=pd.read_csv(CAREER,low_memory=False)
    registry=pd.read_csv(REG,low_memory=False)

    required_s=["Player_ID","Player","Season","G","MP"]
    required_c=["Player_ID","Player","G","MP"]
    for c in required_s:
        if c not in season.columns: raise ValueError(f"Season layer missing {c}")
    for c in required_c:
        if c not in career.columns: raise ValueError(f"Career layer missing {c}")

    # Registry is authoritative for the 46-stat contract.
    if "Statistic" not in registry.columns:
        raise ValueError("46-stat registry is missing Statistic.")
    stats=registry["Statistic"].dropna().astype(str).tolist()
    stats=list(dict.fromkeys(stats))

    # Resolve the source column for each registry statistic. V37's output
    # columns use names such as PTS_per75; registry names are treated as
    # authoritative but matching is case-insensitive.
    def col(df,name):
        if name in df.columns: return name
        matches=[c for c in df.columns if str(c).casefold()==str(name).casefold()]
        return matches[0] if len(matches)==1 else None

    season["Season"]=pd.to_numeric(season["Season"],errors="coerce")
    season["G"]=pd.to_numeric(season["G"],errors="coerce")
    season["MP"]=pd.to_numeric(season["MP"],errors="coerce")
    season["Qualified"]=(
        (season["G"]>=SEASON_MIN_G)&(season["MP"]>=SEASON_MIN_MP)
    )
    season["Era"]=season["Season"].map(era)

    career["G"]=pd.to_numeric(career["G"],errors="coerce")
    career["MP"]=pd.to_numeric(career["MP"],errors="coerce")
    career["Qualified"]=(career["G"]>=CAREER_MIN_G)&(career["MP"]>=CAREER_MIN_MP)

    # Supported stats are those with an actual numeric source column.
    supported_season=[]
    supported_career=[]
    for s in stats:
        if col(season,s) is not None: supported_season.append(s)
        if col(career,s) is not None: supported_career.append(s)

    season_parts=[]
    for s in stats:
        source=col(season,s)
        base=season[["Player_ID","Player","Season","G","MP","Qualified","Era"]].copy()
        base["Statistic"]=s
        base["Value"]=pd.to_numeric(season[source],errors="coerce") if source else np.nan
        higher=s not in LOWER_IS_BETTER
        base["Season_Percentile"]=np.nan
        base["Era_Percentile"]=np.nan
        base["Historical_Percentile"]=np.nan

        q=base["Qualified"]&base["Value"].notna()
        if q.any():
            base.loc[q,"Season_Percentile"]=(
                base.loc[q].groupby("Season")["Value"].transform(
                    lambda z:pct(z,higher)
                )
            )
            base.loc[q,"Era_Percentile"]=(
                base.loc[q].groupby("Era")["Value"].transform(
                    lambda z:pct(z,higher)
                )
            )
            base.loc[q,"Historical_Percentile"]=pct(
                base.loc[q,"Value"],higher
            )
        season_parts.append(base)

    season_long=pd.concat(season_parts,ignore_index=True)
    for c in ["Season_Percentile","Era_Percentile","Historical_Percentile"]:
        season_long[c]=pd.to_numeric(season_long[c],errors="coerce").round(4)

    # Wide season output: exactly one row per Player_ID/Season.
    season_base=season[
        ["Player_ID","Player","Season","G","MP","Qualified","Era"]
    ].groupby(["Player_ID","Season"],as_index=False,sort=False).agg({
        "Player":"first","G":"sum","MP":"sum",
        "Qualified":"first","Era":"first"
    })
    season_wide=season_base.copy()
    for s in stats:
        z=season_long[season_long["Statistic"].eq(s)]
        z=z.groupby(["Player_ID","Season"],as_index=False,sort=False).agg({
            "Value":"first",
            "Season_Percentile":"first",
            "Era_Percentile":"first",
            "Historical_Percentile":"first"
        })
        z=z.set_index(["Player_ID","Season"])
        idx=season_wide.set_index(["Player_ID","Season"]).index
        for c in ["Value","Season_Percentile","Era_Percentile","Historical_Percentile"]:
            season_wide[f"{s}_{c}"]=z[c].reindex(idx).to_numpy()
    season_wide=season_wide.reset_index()

    career_parts=[]
    for s in stats:
        source=col(career,s)
        base=career[["Player_ID","Player","G","MP","Qualified"]].copy()
        base["Statistic"]=s
        base["Value"]=pd.to_numeric(career[source],errors="coerce") if source else np.nan
        higher=s not in LOWER_IS_BETTER
        base["Career_Percentile"]=np.nan
        q=base["Qualified"]&base["Value"].notna()
        if q.any():
            base.loc[q,"Career_Percentile"]=pct(base.loc[q,"Value"],higher)
        career_parts.append(base)

    career_long=pd.concat(career_parts,ignore_index=True)
    career_long["Career_Percentile"]=pd.to_numeric(
        career_long["Career_Percentile"],errors="coerce"
    ).round(4)

    career_wide=career[
        ["Player_ID","Player","G","MP","Qualified"]
    ].drop_duplicates("Player_ID").copy().set_index("Player_ID")
    for s in stats:
        z=career_long[career_long["Statistic"].eq(s)].set_index("Player_ID")
        career_wide[f"{s}_Value"]=z["Value"].reindex(career_wide.index).to_numpy()
        career_wide[f"{s}_Career_Percentile"]=z["Career_Percentile"].reindex(career_wide.index).to_numpy()
    career_wide=career_wide.reset_index()

    # Build an audit/registry describing exactly what is supported.
    reg_out=registry.copy()
    reg_out["Season_Source_Column"]=[
        col(season,s) for s in stats
    ]
    reg_out["Career_Source_Column"]=[
        col(career,s) for s in stats
    ]
    reg_out["Season_Supported"]=reg_out["Season_Source_Column"].notna()
    reg_out["Career_Supported"]=reg_out["Career_Source_Column"].notna()
    reg_out.to_csv(OUT/"playoff_46_stat_percentile_registry_v1.csv",index=False)

    season_long.to_csv(OUT/"playoff_season_46_percentiles_long_v1.csv",index=False)
    season_wide.to_csv(OUT/"playoff_season_46_percentiles_wide_v1.csv",index=False)
    career_long.to_csv(OUT/"playoff_career_46_percentiles_long_v1.csv",index=False)
    career_wide.to_csv(OUT/"playoff_career_46_percentiles_wide_v1.csv",index=False)

    audit=pd.DataFrame([{
        "Registry_Statistics":len(stats),
        "Supported_Season_Statistics":len(supported_season),
        "Unsupported_Season_Statistics":len(stats)-len(supported_season),
        "Supported_Career_Statistics":len(supported_career),
        "Unsupported_Career_Statistics":len(stats)-len(supported_career),
        "Season_Player_Seasons":len(season_wide),
        "Season_Qualified_Player_Seasons":int(season["Qualified"].sum()),
        "Season_Percentile_Long_Rows":len(season_long),
        "Season_Percentile_NonNull":int(season_long["Season_Percentile"].notna().sum()),
        "Era_Percentile_NonNull":int(season_long["Era_Percentile"].notna().sum()),
        "Historical_Percentile_NonNull":int(season_long["Historical_Percentile"].notna().sum()),
        "Career_Players":len(career_wide),
        "Career_Qualified_Players":int(career["Qualified"].sum()),
        "Career_Percentile_Long_Rows":len(career_long),
        "Career_Percentile_NonNull":int(career_long["Career_Percentile"].notna().sum()),
        "Season_Qualification":"G >= 7 AND MP >= 125",
        "Career_Qualification":"G >= 50 AND MP >= 1500",
        "No_Identity_Changes":True,
        "No_Unsupported_Stats_Fabricated":True
    }])
    audit.to_csv(OUT/"playoff_46_percentile_build_audit_v1.csv",index=False)

    print("="*96)
    print("NBA PER-75 — PLAYOFF 46-STAT PERCENTILE LAYER V1")
    print("="*96)
    print(f"Registry statistics:             {len(stats)}")
    print(f"Supported season statistics:     {len(supported_season)}")
    print(f"Unsupported season statistics:   {len(stats)-len(supported_season)}")
    print(f"Supported career statistics:     {len(supported_career)}")
    print(f"Unsupported career statistics:   {len(stats)-len(supported_career)}")
    print(f"Season player-seasons:            {len(season_wide):,}")
    print(f"Season qualified player-seasons:  {int(season['Qualified'].sum()):,}")
    print(f"Career players:                   {len(career_wide):,}")
    print(f"Career qualified players:         {int(career['Qualified'].sum()):,}")
    print()
    print("Non-qualified records remain present; only percentile values are withheld.")
    print("Season contexts: Season / Era / Historical")
    print("Career context: Career")
    print(f"Output: {OUT}")
    print("No identity decisions were changed.")
    print("No unsupported statistics were fabricated.")

if __name__=="__main__":
    main()
