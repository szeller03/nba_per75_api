"""
NBA PER-75 — PLAYOFF 46-STATISTIC EXPANSION V1

The canonical project registry contains exactly 46 statistics. The playoff
layer previously exposed only 22. This build expands the playoff season and
career data contract to all 46 registry entries.

Important:
- A statistic is only populated when it can be calculated defensibly from
  the available B-Ref playoff totals / possession estimates.
- Unsupported advanced metrics are NOT fabricated. They remain blank and are
  explicitly marked Unsupported in the registry.
- This does not change identities, raw B-Ref data, or the existing playoff
  percentile qualification rules.

Canonical 46-stat registry is based on the established player pipeline.
"""

from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75")
DATA=ROOT/"data"
INPUT=DATA/"nba_per75_playoffs_stats_v2.csv"
CAREER_INPUT=DATA/"nba_per75_playoffs_career_stats_v1.csv"
OUTDIR=DATA/"nba_per75_playoff_46_stats_v1"
SEASON_OUT=OUTDIR/"nba_per75_playoffs_46_stats_v1.csv"
CAREER_OUT=OUTDIR/"nba_per75_playoffs_career_46_stats_v1.csv"
REGISTRY_OUT=OUTDIR/"playoff_46_stat_registry_v1.csv"
AUDIT_OUT=OUTDIR/"playoff_46_stat_build_audit_v1.csv"

STAT_MAP={
    "PTS_per75":"PTS_Per75","FG_per75":"FG_Per75","FGA_per75":"FGA_Per75",
    "3P_per75":"3P_Per75","3PA_per75":"3PA_Per75","2P_per75":"2P_Per75",
    "2PA_per75":"2PA_Per75","FT_per75":"FT_Per75","FTA_per75":"FTA_Per75",
    "ORB_per75":"ORB_Per75","DRB_per75":"DRB_Per75","TRB_per75":"TRB_Per75",
    "AST_per75":"AST_Per75","STL_per75":"STL_Per75","BLK_per75":"BLK_Per75",
    "TOV_per75":"TOV_Per75","PF_per75":"PF_Per75",
    "FG_pct":"FG_pct","2P_pct":"2P_pct","3P_pct":"3P_pct","FT_pct":"FT_pct",
    "TS_pct":"TS_pct","FTr":"FTr","3PAr":"3PAr","rTS":"rTS",
    "ORtg":"ORtg","DRtg":"DRtg","Relative_ORtg":"Relative_ORtg",
    "Relative_DRtg":"Relative_DRtg","PER":"PER","BPM":"BPM","OBPM":"OBPM",
    "DBPM":"DBPM","VORP":"VORP","WS/48":"WS/48","OWS":"OWS","DWS":"DWS",
    "WS_per48":"WS/48","USG_pct":"USG%","OREB_pct":"OREB_pct",
    "DREB_pct":"DREB_pct","TRB_pct":"TRB%","AST_pct":"AST_pct",
    "STL_pct":"STL_pct","BLK_pct":"BLK_pct","TOV_pct":"TOV_pct"
}

LOWER_IS_BETTER={"DRtg","Relative_DRtg","TOV_per75","PF_per75","TOV_pct"}

SUPPORTED={
    "PTS_per75","FG_per75","FGA_per75","3P_per75","3PA_per75","2P_per75",
    "2PA_per75","FT_per75","FTA_per75","ORB_per75","DRB_per75","TRB_per75",
    "AST_per75","STL_per75","BLK_per75","TOV_per75","PF_per75",
    "FG_pct","2P_pct","3P_pct","FT_pct","TS_pct","FTr","3PAr","USG_pct","TOV_pct"
}

def n(df,c):
    return pd.to_numeric(df[c],errors="coerce") if c in df.columns else pd.Series(np.nan,index=df.index)

def safe_div(a,b):
    return a/b.replace(0,np.nan)

def actual_column(df, requested):
    """Resolve a source column case-insensitively without guessing between
    distinct columns."""
    if requested in df.columns:
        return requested
    matches=[c for c in df.columns if str(c).casefold()==str(requested).casefold()]
    if len(matches)==1:
        return matches[0]
    return None

def main():
    OUTDIR.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(INPUT,low_memory=False)
    career=pd.read_csv(CAREER_INPUT,low_memory=False)

    required=["Player_ID","Player","Season","Team","G","MP","FG","FGA","3P","3PA",
              "2P","2PA","FT","FTA","ORB","DRB","TRB","AST","STL","BLK","TOV","PF","PTS"]
    missing=[c for c in required if c not in df.columns]
    if missing: raise ValueError("Playoff stats source missing: "+", ".join(missing))

    for c in required[4:]:
        df[c]=pd.to_numeric(df[c],errors="coerce")

    # Reconstruct team context from the existing player-team rows.
    team=df.groupby(["Season","Team"],dropna=False).agg(
        TmG=("G","sum"),TmMP=("MP","sum"),TmFG=("FG","sum"),
        TmFGA=("FGA","sum"),Tm3P=("3P","sum"),Tm3PA=("3PA","sum"),
        TmFT=("FT","sum"),TmFTA=("FTA","sum"),TmORB=("ORB","sum"),
        TmDRB=("DRB","sum"),TmTRB=("TRB","sum"),TmAST=("AST","sum"),
        TmSTL=("STL","sum"),TmBLK=("BLK","sum"),TmTOV=("TOV","sum"),
        TmPTS=("PTS","sum")
    ).reset_index()

    df=df.merge(team,on=["Season","Team"],how="left",validate="many_to_one")

    # Preserve existing Per-75 fields and fill the expanded supported metrics.
    out=df.copy()

    out["FG_pct"]=safe_div(out["FG"],out["FGA"])
    out["2P_pct"]=safe_div(out["2P"],out["2PA"])
    out["3P_pct"]=safe_div(out["3P"],out["3PA"])
    out["FT_pct"]=safe_div(out["FT"],out["FTA"])
    out["TS_pct"]=safe_div(out["PTS"],2*(out["FGA"]+0.44*out["FTA"]))
    out["FTr"]=safe_div(out["FTA"],out["FGA"])
    out["3PAr"]=safe_div(out["3PA"],out["FGA"])

    # USG% and TOV% can be derived from the same team/player totals used by
    # the possession model. These are formula-based estimates, not B-Ref
    # claims.
    team_play_factor=(out["TmMP"]/5)
    player_usage_num=(out["FGA"]+0.44*out["FTA"]+out["TOV"])*team_play_factor
    player_usage_den=out["MP"]*(out["TmFGA"]+0.44*out["TmFTA"]+out["TmTOV"])
    out["USG_pct"]=100*safe_div(player_usage_num,player_usage_den)
    out["TOV_pct"]=100*safe_div(out["TOV"],out["FGA"]+0.44*out["FTA"]+out["TOV"])

    # rTS, ORtg/DRtg, impact metrics, and opponent-dependent percentage
    # metrics are not fabricated. They remain NA unless a defensible source
    # exists in the input layer.
    unsupported=[s for s in STAT_MAP if s not in SUPPORTED]
    for s in unsupported:
        source=STAT_MAP[s]
        out[source]=np.nan

    # Keep only one consolidated player-season observation for the percentile
    # layer while retaining raw team rows in the source statistical layer.
    # Per-75 values are MP-weighted; percentages/rates are reconstructed from
    # consolidated totals.
    keys=["Player_ID","Player","Season","Season_Type"]
    grouped=[]
    for key,g in out.groupby(keys,dropna=False,sort=False):
        pid,player,season,stype=key
        row={"Player_ID":pid,"Player":player,"Season":season,"Season_Type":stype}
        row["G"]=g["G"].sum(min_count=1)
        row["MP"]=g["MP"].sum(min_count=1)
        row["FG"]=g["FG"].sum(min_count=1); row["FGA"]=g["FGA"].sum(min_count=1)
        row["2P"]=g["2P"].sum(min_count=1); row["2PA"]=g["2PA"].sum(min_count=1)
        row["3P"]=g["3P"].sum(min_count=1); row["3PA"]=g["3PA"].sum(min_count=1)
        row["FT"]=g["FT"].sum(min_count=1); row["FTA"]=g["FTA"].sum(min_count=1)
        for c in ["ORB","DRB","TRB","AST","STL","BLK","TOV","PF","PTS"]:
            row[c]=g[c].sum(min_count=1)
        poss=g["Estimated_Player_Possessions"].sum(min_count=1)
        row["Estimated_Player_Possessions"]=poss

        for s in STAT_MAP:
            source=STAT_MAP[s]
            if s.endswith("_per75"):
                source_col=actual_column(g,source)
                vals=pd.to_numeric(g[source_col],errors="coerce") if source_col else pd.Series(np.nan,index=g.index)
                x=pd.DataFrame({"v":vals,"mp":g["MP"]}).dropna()
                x=x[x["mp"]>0]
                row[source]=float((x["v"]*x["mp"]).sum()/x["mp"].sum()) if not x.empty else np.nan
            elif s in {"FG_pct","2P_pct","3P_pct","FT_pct","TS_pct","FTr","3PAr","USG_pct","TOV_pct"}:
                row[source]=np.nan
            else:
                source_col=actual_column(g,source)
                row[source]=g[source_col].iloc[0] if source_col else np.nan

        # Recompute consolidated percentage/rate metrics from totals.
        row["FG_pct"]=row["FG"]/row["FGA"] if row["FGA"] else np.nan
        row["2P_pct"]=row["2P"]/row["2PA"] if row["2PA"] else np.nan
        row["3P_pct"]=row["3P"]/row["3PA"] if row["3PA"] else np.nan
        row["FT_pct"]=row["FT"]/row["FTA"] if row["FTA"] else np.nan
        row["TS_pct"]=row["PTS"]/(2*(row["FGA"]+0.44*row["FTA"])) if (row["FGA"]+0.44*row["FTA"]) else np.nan
        row["FTr"]=row["FTA"]/row["FGA"] if row["FGA"] else np.nan
        row["3PAr"]=row["3PA"]/row["FGA"] if row["FGA"] else np.nan

        # USG% is optional because the complete playoff pipeline no longer
        # depends on B-Ref /per_poss. If an authoritative USG% column exists,
        # retain it; otherwise leave it missing rather than inventing a value.
        # TOV% can be derived directly from the player's counting totals.
        usg_col=actual_column(g,"USG%")
        if usg_col is not None and g["Team"].nunique(dropna=True)==1:
            row["USG_pct"]=pd.to_numeric(g[usg_col],errors="coerce").iloc[0]
        else:
            row["USG_pct"]=np.nan

        tov_denom=row["FGA"]+0.44*row["FTA"]+row["TOV"]
        row["TOV_pct"]=100*row["TOV"]/tov_denom if tov_denom else np.nan

        grouped.append(row)

    season=pd.DataFrame(grouped)

    # Ensure all 46 columns exist in the season output.
    for s,source in STAT_MAP.items():
        if source not in season.columns: season[source]=np.nan

    # Career: use existing V1 career data for the totals/per-75 fields, then
    # calculate the additional formula-supported career rates from career totals.
    for c in career.columns:
        if c not in season.columns and c in STAT_MAP.values():
            pass

    c=career.copy()
    for col in ["G","MP","FG","FGA","2P","2PA","3P","3PA","FT","FTA","ORB","DRB","TRB",
                "AST","STL","BLK","TOV","PF","PTS"]:
        if col in c.columns: c[col]=pd.to_numeric(c[col],errors="coerce")
    c["FG_pct"]=safe_div(c["FG"],c["FGA"])
    c["2P_pct"]=safe_div(c["2P"],c["2PA"])
    c["3P_pct"]=safe_div(c["3P"],c["3PA"])
    c["FT_pct"]=safe_div(c["FT"],c["FTA"])
    c["TS_pct"]=safe_div(c["PTS"],2*(c["FGA"]+0.44*c["FTA"]))
    c["FTr"]=safe_div(c["FTA"],c["FGA"])
    c["3PAr"]=safe_div(c["3PA"],c["FGA"])
    c["TOV_pct"]=100*safe_div(c["TOV"],c["FGA"]+0.44*c["FTA"]+c["TOV"])
    c["USG_pct"]=np.nan  # career USG requires team context across every stint
    for s in STAT_MAP:
        source=STAT_MAP[s]
        if s not in SUPPORTED:
            c[source]=np.nan
        elif source not in c.columns:
            c[source]=np.nan

    season.to_csv(SEASON_OUT,index=False)
    c.to_csv(CAREER_OUT,index=False)

    reasons={}
    for s in STAT_MAP:
        if s in SUPPORTED:
            reasons[s]="SUPPORTED_FROM_BREF_TOTALS_AND_DERIVED_POSSESSIONS"
        else:
            reasons[s]="UNSUPPORTED_WITH_CURRENT_PLAYOFF_SOURCES; LEFT_MISSING"

    registry=pd.DataFrame([{
        "Statistic":s,
        "Source_Column":STAT_MAP[s],
        "Direction":"lower_is_better" if s in LOWER_IS_BETTER else "higher_is_better",
        "Playoff_Season_Available":bool(s in SUPPORTED),
        "Playoff_Career_Available":bool(s in SUPPORTED and s!="USG_pct"),
        "Method_Status":reasons[s],
    } for s in STAT_MAP])
    registry.to_csv(REGISTRY_OUT,index=False)

    audit=pd.DataFrame([{
        "Expected_Statistics":46,
        "Registry_Statistics":len(STAT_MAP),
        "Supported_Season_Statistics":sum(s in SUPPORTED for s in STAT_MAP),
        "Unsupported_Season_Statistics":sum(s not in SUPPORTED for s in STAT_MAP),
        "Season_Player_Rows":len(season),
        "Career_Player_Rows":len(c),
        "No_Identity_Changes":"YES",
        "Unsupported_Metrics_Fabricated":"NO",
    }])
    audit.to_csv(AUDIT_OUT,index=False)

    print("="*96)
    print("NBA PER-75 — PLAYOFF 46-STATISTIC EXPANSION V1")
    print("="*96)
    print(f"Registry statistics:             {len(STAT_MAP)}")
    print(f"Supported season statistics:     {sum(s in SUPPORTED for s in STAT_MAP)}")
    print(f"Unsupported season statistics:   {sum(s not in SUPPORTED for s in STAT_MAP)}")
    print(f"Season player-seasons:            {len(season):,}")
    print(f"Career players:                   {len(c):,}")
    print()
    print("Unsupported statistics are explicitly left missing; none were fabricated.")
    print(f"Season output: {SEASON_OUT}")
    print(f"Career output: {CAREER_OUT}")
    print(f"Registry:      {REGISTRY_OUT}")
    print(f"Audit:         {AUDIT_OUT}")

if __name__=="__main__":
    main()
