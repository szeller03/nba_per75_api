from pathlib import Path
import pandas as pd

ROOT=Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75")
SOURCE=ROOT/"data"/"nba_per75_playoffs_bref_v1.csv"

def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing source: {SOURCE}")
    df=pd.read_csv(SOURCE,low_memory=False)
    required={"Season","Season_Type","Player","G","MP","PTS"}
    missing=required-set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    years=sorted(pd.to_numeric(df["Season"],errors="coerce").dropna().astype(int).unique())
    expected=set(range(1952,2027))
    missing_years=sorted(expected-set(years))
    print("="*88)
    print("NBA PER-75 — BASKETBALL-REFERENCE PLAYOFF SOURCE VALIDATION V1")
    print("="*88)
    print(f"Rows:                  {len(df):,}")
    print(f"Seasons present:       {len(years)}")
    print(f"First season:          {min(years) if years else 'N/A'}")
    print(f"Last season:           {max(years) if years else 'N/A'}")
    print(f"Missing requested:     {missing_years}")
    print(f"Season type values:    {sorted(df['Season_Type'].dropna().astype(str).unique())}")
    print(f"Unique player labels:  {df['Player'].nunique():,}")
    print(f"Required fields:       {'PASSED' if not missing else 'FAILED'}")
    print(f"Full 1952-2026 cover:  {'PASSED' if not missing_years else 'REVIEW'}")

if __name__=="__main__": main()
