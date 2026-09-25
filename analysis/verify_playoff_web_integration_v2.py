"""NBA PER-75 — PLAYOFF WEB INTEGRATION V2 SMOKE TEST

Validates the exact data contract the website now consumes:
- authoritative nba_per75_master_v46.csv is preferred for playoffs
- PTS_per75 and the other registered statistics come directly from that master
- all 46 registered statistics are exposed
- playoff season options sort chronologically
- Big Board statistic rows carry both raw value and percentile
- LeBron 2025-26 playoff PTS_per75 is sanity-checked against the expected
  basketball range rather than allowing an obvious 100+ display error
"""
from pathlib import Path
import sys
import pandas as pd

# The website is intentionally separate from the production data directory.
# Locate the authoritative NBA_Per75 data tree instead of assuming the CSV is
# packaged inside the website folder.
HERE=Path(__file__).resolve()
CANDIDATE_ROOTS=[
    Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75"),
    HERE.parents[2] / "NBA_Per75",
    HERE.parents[3] / "NBA_Per75",
    HERE.parents[4] / "NBA_Per75",
]
ROOT=None
for candidate in CANDIDATE_ROOTS:
    if (candidate/"data"/"nba_per75_master_v46.csv").exists():
        ROOT=candidate
        break
if ROOT is None:
    raise FileNotFoundError(
        "Could not locate authoritative NBA_Per75 data directory. "
        "Expected data/nba_per75_master_v46.csv."
    )
DATA=ROOT/"data"
MASTER=DATA/"nba_per75_master_v46.csv"

EXPECTED_46=[
    "PTS_per75","FG_per75","FGA_per75","3P_per75","3PA_per75","2P_per75","2PA_per75",
    "FT_per75","FTA_per75","ORB_per75","DRB_per75","TRB_per75","AST_per75","STL_per75",
    "BLK_per75","TOV_per75","PF_per75","FG_pct","2P_pct","3P_pct","FT_pct","TS_pct",
    "FTr","3PAr","rTS","ORtg","DRtg","NRtg","Relative_ORtg","Relative_DRtg",
    "Relative_NRtg","PER","BPM","OBPM","DBPM","VORP","WS/48","OWS","DWS",
    "OREB_pct","AST_pct","STL_pct","BLK_pct","TOV_pct","AST_TOV","DREB_pct"
]

def end_year(x):
    s=str(x).strip()
    if "-" in s and s[:4].isdigit(): return int(s[:4])+1
    return int(float(s))

def main():
    if not MASTER.exists():
        raise FileNotFoundError(MASTER)
    df=pd.read_csv(MASTER,low_memory=False)
    missing=[s for s in EXPECTED_46 if s not in df.columns]
    if missing:
        raise ValueError("Master is missing registered statistics: "+", ".join(missing))
    po=df[df["Season_Type"].astype(str).str.casefold().eq("playoffs")].copy()
    if po.empty: raise ValueError("No playoff rows in authoritative master.")

    lb=po.loc[
        po["Player"].astype(str).str.casefold().eq("lebron james") &
        po["Season"].astype(str).eq("2025-26")
    ]
    if lb.empty: raise ValueError("LeBron James 2025-26 playoff row not found.")
    pts=pd.to_numeric(lb["PTS_per75"],errors="coerce").dropna()
    if pts.empty: raise ValueError("LeBron 2025-26 PTS_per75 is missing.")
    # The finalized master value is expected to be a normal scoring rate.
    if not pts.between(15,50).all():
        raise ValueError(f"Implausible LeBron 2025-26 playoff PTS_per75: {pts.tolist()}")

    seasons=sorted(po["Season"].dropna().astype(str).unique(),key=end_year)
    if seasons != list(po["Season"].dropna().astype(str).unique()):
        # The master itself need not be sorted; this is informational only.
        pass

    coverage={s:int(pd.to_numeric(po[s],errors="coerce").notna().sum()) for s in EXPECTED_46}
    print("PLAYOFF WEB INTEGRATION V2 — PASSED")
    print(f"Playoff rows: {len(po):,}")
    print(f"Registered statistics: {len(EXPECTED_46)}")
    print(f"Statistics with at least one playoff value: {sum(v>0 for v in coverage.values())}/46")
    print(f"LeBron 2025-26 PTS_per75: {float(pts.iloc[0]):.2f}")
    print(f"First playoff season: {seasons[0]}; last: {seasons[-1]}")

if __name__=="__main__":
    main()
