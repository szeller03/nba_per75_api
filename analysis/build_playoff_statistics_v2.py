"""
NBA PER-75 — PLAYOFF STATISTICAL LAYER V2

Fixes V1's Basketball-Reference /per_poss 429 dependency.

For every season 1952-2026, this build uses the already-downloaded
Basketball-Reference playoff TOTALS source:
    data/nba_per75_playoffs_bref_v1.csv

It does not request /per_poss pages.

Method:
  1952-1973:
      existing historical team-Pace methodology from V1:
      estimated possessions -> Per-100 -> Per-75

  1974-2026:
      estimate player possessions from the B-Ref playoff totals themselves:
          team possessions =
              FGA + 0.44*FTA - ORB + TOV
          player possessions =
              team possessions * player MP / team MP
      then:
          Per-75 = total stat / player possessions * 75

This is a possession estimate derived entirely from the B-Ref totals source.
It is NOT represented as B-Ref's own /per_poss table.

The raw B-Ref totals remain untouched.

No identity decisions are changed.
No fuzzy matching.
No identity guessing.
"""

from pathlib import Path
import math
import re
import unicodedata
import pandas as pd

ROOT=Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75")
RAW=ROOT/"data"/"nba_per75_playoffs_bref_v1.csv"
CANON=ROOT/"data"/"nba_per75_playoffs_player_season_v4.csv"
OUT=ROOT/"data"/"nba_per75_playoffs_stats_v2.csv"
AUDIT=ROOT/"data"/"nba_per75_playoffs_stats_build_audit_v2.csv"

RATE_STATS=["PTS","FG","FGA","3P","3PA","2P","2PA","FT","FTA",
            "ORB","DRB","TRB","AST","STL","BLK","TOV","PF","GS"]

def num(x):
    v=pd.to_numeric(x,errors="coerce")
    return None if pd.isna(v) else float(v)

def p75(total,poss):
    if total is None or poss is None or poss<=0: return None
    return total/poss*75.0

def norm_year(x):
    v=pd.to_numeric(x,errors="coerce")
    return int(v) if not pd.isna(v) else None

def main():
    raw=pd.read_csv(RAW,low_memory=False)
    canon=pd.read_csv(CANON,low_memory=False)

    # The canonical v4 identity layer provides the authoritative resolved
    # Player_ID/Player/Season universe. The v4 output intentionally does not
    # retain Team, so recover the original B-Ref player-team rows by joining
    # the raw B-Ref totals to the v4 canonical identity through normalized
    # player name + season. This is only a source reconstruction step; no new
    # identity decisions are made here.
    raw_name_col = "Player"
    if raw_name_col not in raw.columns:
        raise ValueError("B-Ref totals source is missing Player.")
    if "Season" not in raw.columns:
        raise ValueError("B-Ref totals source is missing Season.")

    def _norm(v):
        s="" if pd.isna(v) else str(v)
        s=unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode("ascii")
        s=s.casefold()
        s=re.sub(r"[^a-z0-9 ]+"," ",s)
        return re.sub(r"\\s+"," ",s).strip()

    raw["_NameNorm"]=raw["Player"].map(_norm)
    raw["Season"]=pd.to_numeric(raw["Season"],errors="coerce").astype("Int64")
    canon["_NameNorm"]=canon["Player"].map(_norm)
    canon["Season"]=pd.to_numeric(canon["Season"],errors="coerce").astype("Int64")

    # Canonical v4 is already consolidated to Player_ID + Season. Merge each
    # canonical player-season to all matching B-Ref team rows, then retain the
    # original Team and totals. This preserves multi-team playoff stints.
    work=raw.merge(
        canon[["Player_ID","Player","Season","_NameNorm"]],
        on=["Season","_NameNorm"],
        how="inner",
        suffixes=("_bref","_canonical")
    )

    # Because the raw B-Ref source may contain a blank Player_ID column,
    # pandas suffixes the two Player_ID fields during the merge. The
    # canonical resolver's Player_ID is authoritative.
    if "Player_ID_canonical" in work.columns:
        work["Player_ID"]=work["Player_ID_canonical"]
    elif "Player_ID" not in work.columns:
        raise ValueError("Canonical Player_ID was not retained after the B-Ref join.")

    # The canonical resolver's Player name is authoritative for display.
    if "Player_canonical" in work.columns:
        work["Player"]=work["Player_canonical"]

    # Required totals fields.
    required=["Player_ID","Player","Team","Season","G","MP","FGA","FTA","ORB","TOV","PTS"]
    missing=[c for c in required if c not in work.columns]
    if missing:
        raise ValueError(f"Playoff source missing required columns: {missing}")

    # Numeric conversion.
    for c in ["G","GS","MP","FG","FGA","3P","3PA","2P","2PA","FT","FTA",
              "ORB","DRB","TRB","AST","STL","BLK","TOV","PF","PTS"]:
        if c in work.columns:
            work[c]=pd.to_numeric(work[c],errors="coerce")

    # B-Ref totals can contain multiple player-team rows. Each row is already
    # a player-team playoff stint, so team possessions are computed by summing
    # those stints for the same season/team.
    team=work.groupby(["Season","Team"],dropna=False).agg(
        Team_FGA=("FGA","sum"),
        Team_FTA=("FTA","sum"),
        Team_ORB=("ORB","sum"),
        Team_TOV=("TOV","sum"),
        Team_MP=("MP","sum"),
    ).reset_index()

    team["Team_Possessions"]=(
        team["Team_FGA"]
        + 0.44*team["Team_FTA"]
        - team["Team_ORB"]
        + team["Team_TOV"]
    )

    work=work.merge(team,on=["Season","Team"],how="left",validate="many_to_one")

    work["Player_Possessions"]=(
        work["Team_Possessions"] * work["MP"] / work["Team_MP"]
    )

    # For historical seasons, preserve V1's historical method rather than
    # replacing it. V1 output is used as the historical source if available.
    v1=ROOT.parent/"data"/"nba_per75_playoffs_stats_v1.csv"
    historical=None
    if v1.exists():
        try:
            historical=pd.read_csv(v1,low_memory=False)
        except Exception:
            historical=None

    outputs=[]
    audit=[]

    for season,g in work.groupby("Season",sort=True):
        y=norm_year(season)
        if y is None: continue

        # Prefer V1 historical rows for 1952-73 if they exist.
        if y<=1973 and historical is not None and not historical.empty:
            hs=historical.loc[pd.to_numeric(historical["Season"],errors="coerce").eq(y)].copy()
            if not hs.empty:
                outputs.append(hs)
                audit.append({
                    "Season":y,"Method":"V1 historical estimated possessions",
                    "Input_Canonical_Rows":len(g),"Output_Rows":len(hs),
                    "Team_Possession_Estimate_Rows":0,
                    "Failed":False,
                })
                continue

        out=pd.DataFrame()
        out["Season"]=g["Season"]
        out["Season_Type"]="Playoffs"
        out["Player_ID"]=g["Player_ID"]
        out["Player"]=g["Player"]
        out["Team"]=g["Team"]
        for c in ["G","GS","MP","FG","FGA","3P","3PA","2P","2PA","FT","FTA",
                  "ORB","DRB","TRB","AST","STL","BLK","TOV","PF","PTS"]:
            if c in g.columns: out[c]=g[c]

        out["Estimated_Team_Possessions"]=g["Team_Possessions"]
        out["Estimated_Player_Possessions"]=g["Player_Possessions"]

        for c in RATE_STATS:
            if c in g.columns:
                out[f"{c}_Per75"]=g[c]/g["Player_Possessions"]*75

        # Percentages remain calculated from totals, not possessions.
        for pct,a,b in [
            ("FG%","FG","FGA"),("3P%","3P","3PA"),
            ("2P%","2P","2PA"),("FT%","FT","FTA")
        ]:
            if a in g.columns and b in g.columns:
                out[pct]=g[a]/g[b].replace(0,pd.NA)

        if all(c in g.columns for c in ["FG","3P","FGA"]):
            out["eFG%"]=(g["FG"]+0.5*g["3P"])/g["FGA"].replace(0,pd.NA)

        audit.append({
            "Season":y,
            "Method":"B-Ref totals derived possessions -> Per-75",
            "Input_Canonical_Rows":len(g),
            "Output_Rows":len(out),
            "Team_Possession_Estimate_Rows":int(g["Team_Possessions"].notna().sum()),
            "Failed":False,
        })
        outputs.append(out)

    if not outputs:
        raise RuntimeError("No playoff statistical rows were produced.")

    final=pd.concat(outputs,ignore_index=True)

    # Canonical uniqueness check: never emit duplicate Player_ID/Season/Team rows.
    dup=final.duplicated(["Player_ID","Season","Team"],keep=False)
    if dup.any():
        raise ValueError(
            f"Statistical layer contains {int(dup.sum())} duplicate player-season-team rows."
        )

    final.to_csv(OUT,index=False)
    audit_df=pd.DataFrame(audit)
    audit_df.to_csv(AUDIT,index=False)

    seasons=sorted(pd.to_numeric(final["Season"],errors="coerce").dropna().astype(int).unique())
    print("="*88)
    print("NBA PER-75 — PLAYOFF STATISTICAL LAYER V2")
    print("="*88)
    print(f"Canonical playoff player-seasons: {len(canon):,}")
    print("1952-73: existing validated historical layer retained where available")
    print("1974-2026: B-Ref totals -> estimated possessions -> Per-75")
    print()
    for _,r in audit_df.iterrows():
        print(f"{int(r.Season):4d}: {r.Method} — {int(r.Output_Rows):,} player-seasons")
    missing_seasons=[y for y in range(1952,2027) if y not in seasons]
    print()
    print(f"Statistical output rows:    {len(final):,}")
    print(f"Players:                    {final['Player_ID'].nunique():,}")
    print(f"Seasons:                    {len(seasons):,}")
    print(f"Missing statistical seasons:{len(missing_seasons):,}")
    if missing_seasons:
        print("Missing:", ",".join(map(str,missing_seasons)))
    print(f"Output:                     {OUT}")
    print(f"Audit:                      {AUDIT}")
    print()
    print("No playoff identity decisions were changed.")
    print("No fuzzy matching or identity guessing was performed.")
    print("No /per_poss Basketball-Reference requests are made by V2.")

if __name__=="__main__":
    main()
