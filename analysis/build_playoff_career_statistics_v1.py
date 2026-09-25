"""
NBA PER-75 — PLAYOFF CAREER STATISTICAL LAYER V1

Builds playoff career statistics from the complete season/team playoff
statistical layer:

data/nba_per75_playoffs_stats_v2.csv

Career rate statistics are calculated from career totals and career estimated
possessions. They are NOT arithmetic averages of season Per-75 values.

The layer preserves:
- Player_ID
- Player
- first/last playoff season
- playoff seasons
- games, starts, minutes
- counting totals
- estimated possessions
- career Per-75 statistics
- shooting percentages

No percentile qualification is performed here.
No identity decisions are changed.
"""

from pathlib import Path
import pandas as pd

ROOT=Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75")
INPUT=ROOT/"data"/"nba_per75_playoffs_stats_v2.csv"
OUTPUT=ROOT/"data"/"nba_per75_playoffs_career_stats_v1.csv"
AUDIT=ROOT/"data"/"nba_per75_playoffs_career_stats_build_audit_v1.csv"

COUNTING=[
    "G","GS","MP","FG","FGA","3P","3PA","2P","2PA","FT","FTA",
    "ORB","DRB","TRB","AST","STL","BLK","TOV","PF","PTS"
]
RATE_BASE=[
    "FG","FGA","3P","3PA","2P","2PA","FT","FTA",
    "ORB","DRB","TRB","AST","STL","BLK","TOV","PF","PTS"
]

def main():
    df=pd.read_csv(INPUT,low_memory=False)

    required=["Player_ID","Player","Season","G","MP","PTS"]
    missing=[c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Playoff statistical layer missing required columns: {missing}")

    df["Season"]=pd.to_numeric(df["Season"],errors="coerce")
    for c in COUNTING + ["Estimated_Player_Possessions"]:
        if c in df.columns:
            df[c]=pd.to_numeric(df[c],errors="coerce")

    # A Player_ID/Season may have multiple team rows. Career aggregation sums
    # those underlying rows. This is intentional and avoids averaging team
    # stint rates.
    rows=[]
    for pid,g in df.groupby("Player_ID",dropna=False,sort=True):
        g=g.sort_values(["Season","Player"],kind="stable")
        out={
            "Player_ID":str(pid),
            "Player":str(g["Player"].dropna().iloc[0]) if g["Player"].notna().any() else "",
            "Season_Type":"Playoffs",
            "First_Playoff_Season":int(g["Season"].min()),
            "Last_Playoff_Season":int(g["Season"].max()),
            "Playoff_Seasons":int(g["Season"].nunique()),
        }

        for c in COUNTING:
            if c in g.columns:
                vals=g[c]
                out[c]=float(vals.sum(min_count=1)) if vals.notna().any() else None

        if "Estimated_Player_Possessions" in g.columns:
            poss=g["Estimated_Player_Possessions"]
            out["Estimated_Player_Possessions"]=float(
                poss.sum(min_count=1)
            ) if poss.notna().any() else None
        else:
            out["Estimated_Player_Possessions"]=None

        poss=out["Estimated_Player_Possessions"]

        # Career Per-75 is derived from career totals / career possessions.
        for c in RATE_BASE:
            value=out.get(c)
            if value is not None and poss is not None and poss>0:
                out[f"{c}_Per75"]=value/poss*75
            else:
                # Historical source gaps are valid missing values. Do not
                # attempt to treat an unavailable statistic as zero.
                out[f"{c}_Per75"]=None

        # Shooting percentages use career totals, not averages of season/team
        # percentages.
        for pct,a,b in [
            ("FG%","FG","FGA"),
            ("3P%","3P","3PA"),
            ("2P%","2P","2PA"),
            ("FT%","FT","FTA"),
        ]:
            aa=out.get(a); bb=out.get(b)
            out[pct]=aa/bb if aa is not None and bb not in (None,0) else None

        fg=out.get("FG"); th=out.get("3P"); fga=out.get("FGA")
        out["eFG%"]=(fg+0.5*th)/fga if (
            fg is not None and th is not None and fga not in (None,0)
        ) else None

        # Keep useful context counts.
        if "Team" in g.columns:
            out["Playoff_Teams"]=int(g["Team"].nunique(dropna=True))

        rows.append(out)

    career=pd.DataFrame(rows)

    # Stable ordering and uniqueness checks.
    career=career.sort_values(["Player","Player_ID"],kind="stable").reset_index(drop=True)
    if career["Player_ID"].duplicated().any():
        raise ValueError("Career output contains duplicate Player_ID rows.")

    career.to_csv(OUTPUT,index=False)

    audit=pd.DataFrame([{
        "Input_Playoff_Rows":len(df),
        "Input_Players":df["Player_ID"].nunique(),
        "Input_Seasons":df["Season"].nunique(),
        "Career_Output_Rows":len(career),
        "Career_Output_Players":career["Player_ID"].nunique(),
        "Career_Output_Seasons_Covered":int(career["Playoff_Seasons"].sum()),
        "Players_With_Estimated_Possessions":int(career["Estimated_Player_Possessions"].notna().sum()),
        "Players_With_Career_PTS_Per75":int(career["PTS_Per75"].notna().sum()),
        "Method":"Career totals / career estimated playoff possessions * 75",
        "Percentile_Qualification":"NOT CALCULATED IN THIS LAYER",
        "Identity_Decisions_Changed":"NO",
        "Fuzzy_Matching":"NO",
    }])
    audit.to_csv(AUDIT,index=False)

    print("="*88)
    print("NBA PER-75 — PLAYOFF CAREER STATISTICAL LAYER V1")
    print("="*88)
    print(f"Input playoff rows:              {len(df):,}")
    print(f"Input playoff players:            {df['Player_ID'].nunique():,}")
    print(f"Career player rows:               {len(career):,}")
    print(f"Players with career possessions:  {career['Estimated_Player_Possessions'].notna().sum():,}")
    print(f"Players with career PTS Per-75:   {career['PTS_Per75'].notna().sum():,}")
    print(f"Output:                            {OUTPUT}")
    print(f"Audit:                             {AUDIT}")
    print()
    print("Career Per-75 uses career totals divided by career estimated possessions.")
    print("It is NOT an average of season Per-75 values.")
    print("No percentile qualification is calculated yet.")
    print("No identity decisions were changed.")

if __name__=="__main__":
    main()
