"""
NBA PER-75 — PLAYOFF PERCENTILE LAYER V1

Builds playoff season and career percentiles without altering the underlying
playoff statistics.

Season qualification:
    G >= 7 AND MP >= 125

Career qualification:
    G >= 50 AND MP >= 1,500

These thresholds are the project's established playoff leaderboard definitions.

Important behavior:
- Every playoff player-season remains in the season output.
- A non-qualified season keeps its raw/statistical values but receives no
  percentile values.
- Career statistics remain available for every player.
- Career percentiles are assigned only to career-qualified players.
- Season, Era, and Historical contexts are separate.
- Percentile ranking follows the established project method:
      percentile = 100 * (n - average_rank) / (n - 1)
  with higher-is-better statistics ranked descending and lower-is-better
  statistics inverted.
- One-observation populations receive 100.
- Missing values remain missing.

The available playoff statistic universe is discovered from the V2 playoff
statistical layer rather than forcing unavailable regular-season-only metrics
into playoff percentiles.
"""

from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75")
DATA=ROOT/"data"
SEASON_FILE=DATA/"nba_per75_playoffs_stats_v2.csv"
CAREER_FILE=DATA/"nba_per75_playoffs_career_stats_v1.csv"

OUTDIR=DATA/"nba_per75_playoff_percentiles_v1"
SEASON_LONG=OUTDIR/"playoff_season_percentiles_long_v1.csv"
SEASON_WIDE=OUTDIR/"playoff_season_percentiles_wide_v1.csv"
CAREER_LONG=OUTDIR/"playoff_career_percentiles_long_v1.csv"
CAREER_WIDE=OUTDIR/"playoff_career_percentiles_wide_v1.csv"
REGISTRY=OUTDIR/"playoff_percentile_statistic_registry_v1.csv"
AUDIT=OUTDIR/"playoff_percentile_build_audit_v1.csv"

SEASON_MIN_GAMES=7
SEASON_MIN_MP=125
CAREER_MIN_GAMES=50
CAREER_MIN_MP=1500

LOWER_IS_BETTER={
    "TOV_Per75","PF_Per75"
}

ERA_BANDS=[
    ("1951-52_to_1969-70",1952,1970),
    ("1970-71_to_1979-80",1971,1980),
    ("1980-81_to_1989-90",1981,1990),
    ("1990-91_to_1999-00",1991,2000),
    ("2000-01_to_2009-10",2001,2010),
    ("2010-11_to_2019-20",2011,2020),
    ("2020-21_to_2025-26",2021,2026),
]

def num(s):
    return pd.to_numeric(s,errors="coerce")

def resolve_era(year):
    y=num(year)
    if pd.isna(y): return "UNRESOLVED"
    y=int(y)
    for label,start,end in ERA_BANDS:
        if start<=y<=end:
            return label
    return "UNRESOLVED"

def percentile_rank(series,higher=True):
    x=num(series)
    out=pd.Series(np.nan,index=series.index,dtype="float64")
    valid=x.notna()
    n=int(valid.sum())
    if n==0: return out
    if n==1:
        out.loc[valid]=100.0
        return out
    # Established project convention: average rank, with higher values
    # receiving better ranks when higher=True.
    ranks=x.loc[valid].rank(method="average",ascending=higher)
    out.loc[valid]=100.0*(n-ranks)/(n-1)
    return out

def available_stats(df):
    # Include actual Per-75 statistics and shooting percentages. Do not
    # percentile-rank totals, minutes, games, or possession estimates.
    preferred=[
        "PTS_Per75","FG_Per75","FGA_Per75","3P_Per75","3PA_Per75",
        "2P_Per75","2PA_Per75","FT_Per75","FTA_Per75",
        "ORB_Per75","DRB_Per75","TRB_Per75","AST_Per75","STL_Per75",
        "BLK_Per75","TOV_Per75","PF_Per75",
        "FG%","2P%","3P%","FT%","eFG%"
    ]
    return [s for s in preferred if s in df.columns]

def build_season(season):
    df=season.copy()
    df["Season"]=num(df["Season"])
    df["G"]=num(df["G"])
    df["MP"]=num(df["MP"])
    df["Season_Qualified"]=(
        (df["G"]>=SEASON_MIN_GAMES) &
        (df["MP"]>=SEASON_MIN_MP)
    )
    df["Era"]=df["Season"].map(resolve_era)

    stats=available_stats(df)
    parts=[]

    for stat in stats:
        temp=df[[
            "Player_ID","Player","Season","Season_Type","G","MP",
            "Season_Qualified","Era"
        ]].copy()
        temp["Statistic"]=stat
        temp["Value"]=num(df[stat])
        temp["Higher_Is_Better"]=not (stat in LOWER_IS_BETTER)

        # Percentiles are only calculated inside the qualified population.
        q=temp["Season_Qualified"] & temp["Value"].notna()

        temp["Season_Percentile"]=np.nan
        temp["Era_Percentile"]=np.nan
        temp["Historical_Percentile"]=np.nan

        if q.any():
            temp.loc[q,"Season_Percentile"]=(
                temp.loc[q].groupby("Season",sort=False)["Value"]
                .transform(
                    lambda s: percentile_rank(
                        s, higher=not (stat in LOWER_IS_BETTER)
                    )
                )
            )
            temp.loc[q,"Era_Percentile"]=(
                temp.loc[q].groupby("Era",sort=False)["Value"]
                .transform(
                    lambda s: percentile_rank(
                        s, higher=not (stat in LOWER_IS_BETTER)
                    )
                )
            )
            temp.loc[q,"Historical_Percentile"]=percentile_rank(
                temp.loc[q,"Value"],
                higher=not (stat in LOWER_IS_BETTER)
            )

        parts.append(temp)

    long=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
    for c in ["Season_Percentile","Era_Percentile","Historical_Percentile"]:
        if c in long.columns:
            long[c]=num(long[c]).round(4)

    # Wide percentile/value contract.
    if not long.empty:
        # B-Ref can contain multiple team rows for the same canonical
        # Player_ID/Season. The percentile layer is player-season based, so
        # collapse those duplicate keys before building the wide table.
        key_cols=["Player_ID","Season","Season_Type"]
        base=df[[
            "Player_ID","Player","Season","Season_Type","G","MP",
            "Season_Qualified","Era"
        ]].copy()

        def first_nonnull(s):
            s=s.dropna()
            return s.iloc[0] if not s.empty else np.nan

        base=base.groupby(key_cols,as_index=False,sort=False).agg({
            "Player":"first",
            "G":"sum",
            "MP":"sum",
            "Season_Qualified":"first",
            "Era":"first",
        })
        wide=base.copy()

        for stat in stats:
            s=long[long["Statistic"].eq(stat)].copy()
            s=s.groupby(key_cols,as_index=False,sort=False).agg({
                "Value":first_nonnull,
                "Season_Percentile":first_nonnull,
                "Era_Percentile":first_nonnull,
                "Historical_Percentile":first_nonnull,
            })
            s=s.set_index(key_cols)
            key=wide.set_index(key_cols).index
            for col in ["Value","Season_Percentile","Era_Percentile","Historical_Percentile"]:
                vals=s[col].reindex(key).to_numpy()
                wide[f"{stat}_{col}"]=vals
        wide=wide.reset_index()
    else:
        wide=pd.DataFrame()

    if not wide.empty and wide.duplicated(["Player_ID","Season","Season_Type"]).any():
        raise ValueError("Season percentile wide output still contains duplicate Player_ID/Season rows.")
    return long,wide,stats

def build_career(career):
    df=career.copy()
    df["G"]=num(df["G"])
    df["MP"]=num(df["MP"])
    df["Career_Qualified"]=(
        (df["G"]>=CAREER_MIN_GAMES) &
        (df["MP"]>=CAREER_MIN_MP)
    )

    stats=available_stats(df)
    parts=[]

    for stat in stats:
        temp=df[[
            "Player_ID","Player","Season_Type","First_Playoff_Season",
            "Last_Playoff_Season","Playoff_Seasons","G","MP",
            "Career_Qualified"
        ]].copy()
        temp["Statistic"]=stat
        temp["Value"]=num(df[stat])
        temp["Higher_Is_Better"]=not (stat in LOWER_IS_BETTER)
        temp["Career_Percentile"]=np.nan

        q=temp["Career_Qualified"] & temp["Value"].notna()
        if q.any():
            temp.loc[q,"Career_Percentile"]=percentile_rank(
                temp.loc[q,"Value"],
                higher=not (stat in LOWER_IS_BETTER)
            )

        parts.append(temp)

    long=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
    if not long.empty:
        long["Career_Percentile"]=num(long["Career_Percentile"]).round(4)

        wide=df[[
            "Player_ID","Player","Season_Type","First_Playoff_Season",
            "Last_Playoff_Season","Playoff_Seasons","G","MP",
            "Career_Qualified"
        ]].drop_duplicates("Player_ID").copy()
        wide=wide.set_index("Player_ID")
        for stat in stats:
            s=long[long["Statistic"].eq(stat)].set_index("Player_ID")
            wide[f"{stat}_Value"]=s["Value"].reindex(wide.index).to_numpy()
            wide[f"{stat}_Career_Percentile"]=s["Career_Percentile"].reindex(wide.index).to_numpy()
        wide=wide.reset_index()
    else:
        wide=pd.DataFrame()

    return long,wide,stats

def main():
    OUTDIR.mkdir(parents=True,exist_ok=True)

    if not SEASON_FILE.exists():
        raise FileNotFoundError(SEASON_FILE)
    if not CAREER_FILE.exists():
        raise FileNotFoundError(CAREER_FILE)

    season=pd.read_csv(SEASON_FILE,low_memory=False)
    career=pd.read_csv(CAREER_FILE,low_memory=False)

    for required,name in [
        (["Player_ID","Player","Season","Season_Type","G","MP"],"playoff season stats"),
        (["Player_ID","Player","Season_Type","G","MP"],"playoff career stats"),
    ]:
        df=season if name=="playoff season stats" else career
        missing=[c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"{name} missing required columns: {missing}")

    sl,sw,sstats=build_season(season)
    cl,cw,cstats=build_career(career)

    sl.to_csv(SEASON_LONG,index=False)
    sw.to_csv(SEASON_WIDE,index=False)
    cl.to_csv(CAREER_LONG,index=False)
    cw.to_csv(CAREER_WIDE,index=False)

    all_stats=sorted(set(sstats)|set(cstats))
    registry=pd.DataFrame([{
        "Statistic":s,
        "Season_Available":s in sstats,
        "Career_Available":s in cstats,
        "Higher_Is_Better":not(s in LOWER_IS_BETTER),
        "Season_Qualification":f"G >= {SEASON_MIN_GAMES} AND MP >= {SEASON_MIN_MP}",
        "Career_Qualification":f"G >= {CAREER_MIN_GAMES} AND MP >= {CAREER_MIN_MP}",
    } for s in all_stats])
    registry.to_csv(REGISTRY,index=False)

    audit=pd.DataFrame([{
        "Season_Input_Rows":len(season),
        "Season_Input_Players":season["Player_ID"].nunique(),
        "Season_Input_Seasons":season["Season"].nunique(),
        "Season_Qualified_Rows":int(
            ((num(season["G"])>=SEASON_MIN_GAMES)&
             (num(season["MP"])>=SEASON_MIN_MP)).sum()
        ),
        "Season_Long_Rows":len(sl),
        "Season_Wide_Rows":len(sw),
        "Season_Statistics":len(sstats),
        "Season_Percentile_NonNull":int(sl["Season_Percentile"].notna().sum()),
        "Era_Percentile_NonNull":int(sl["Era_Percentile"].notna().sum()),
        "Historical_Percentile_NonNull":int(sl["Historical_Percentile"].notna().sum()),
        "Career_Input_Players":career["Player_ID"].nunique(),
        "Career_Qualified_Players":int(
            ((num(career["G"])>=CAREER_MIN_GAMES)&
             (num(career["MP"])>=CAREER_MIN_MP)).sum()
        ),
        "Career_Long_Rows":len(cl),
        "Career_Wide_Rows":len(cw),
        "Career_Statistics":len(cstats),
        "Career_Percentile_NonNull":int(cl["Career_Percentile"].notna().sum()),
        "Season_Qualification":"G >= 7 AND MP >= 125",
        "Career_Qualification":"G >= 50 AND MP >= 1500",
        "Identity_Decisions_Changed":"NO",
        "Underlying_Data_Overwritten":"NO",
    }])
    audit.to_csv(AUDIT,index=False)

    print("="*96)
    print("NBA PER-75 — PLAYOFF PERCENTILE LAYER V1")
    print("="*96)
    print(f"Season input rows:              {len(season):,}")
    print(f"Season statistics:              {len(sstats):,}")
    print(f"Season qualified rows:          {int(((num(season['G'])>=SEASON_MIN_GAMES)&(num(season['MP'])>=SEASON_MIN_MP)).sum()):,}")
    print(f"Season percentile long rows:    {len(sl):,}")
    print(f"Career input players:           {career['Player_ID'].nunique():,}")
    print(f"Career statistics:              {len(cstats):,}")
    print(f"Career qualified players:       {int(((num(career['G'])>=CAREER_MIN_GAMES)&(num(career['MP'])>=CAREER_MIN_MP)).sum()):,}")
    print(f"Career percentile long rows:    {len(cl):,}")
    print()
    print("Season qualification: G >= 7 AND MP >= 125")
    print("Career qualification: G >= 50 AND MP >= 1,500")
    print("Non-qualified seasons retain statistics but receive no percentile.")
    print("Non-qualified careers retain statistics but receive no career percentile.")
    print("Contexts: Season / Era / Historical")
    print(f"Output directory: {OUTDIR}")
    print(f"Audit:            {AUDIT}")
    print("No identity decisions were changed.")
    print("Underlying playoff statistics were NOT overwritten.")

if __name__=="__main__":
    main()
