"""Validate the Phase 3 playoff SDI rebuild."""

from pathlib import Path
import json, sys
import pandas as pd


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    target = root / "local_api" / "cache" / "playoff_sdi_v4_player_seasons.csv"
    report = root / "data" / "playoff_sdi_fix_phase3_report.json"

    errors = []
    if not target.exists(): errors.append("playoff SDI output missing")
    if not report.exists(): errors.append("phase 3 report missing")
    if errors:
        print("STATUS: FAIL")
        for e in errors: print(" -", e)
        raise SystemExit(1)

    df = pd.read_csv(target, low_memory=False)
    rep = json.loads(report.read_text(encoding="utf-8"))

    required = ["Player_ID","Player","Season","Season_Type","G","MP",
                "Scoring_Volume","Defense","Rebounding","Creation_Playmaking",
                "Efficiency","Impact_Value","SDI_v4_Playoffs"]
    for c in required:
        if c not in df.columns: errors.append(f"missing column: {c}")

    g = pd.to_numeric(df["G"], errors="coerce")
    mp = pd.to_numeric(df["MP"], errors="coerce")
    sdi = pd.to_numeric(df["SDI_v4_Playoffs"], errors="coerce")

    if ((g < 4) | (mp < 75)).any():
        errors.append("unqualified playoff records present")
    if sdi.isna().any():
        errors.append("null playoff SDI values present")
    if ((sdi < 0) | (sdi > 100)).any():
        errors.append("playoff SDI outside 0-100")

    if errors:
        print("STATUS: FAIL")
        for e in errors: print(" -", e)
        raise SystemExit(1)

    print("STATUS: PASS")
    print(f"Rows: {len(df):,}")
    print("Qualification: G >= 4 and MP >= 75")
    print("Defense activity: STL/75 40%, BLK/75 60%")
    print("Regular-season SDI and peak files were not validated or modified here.")


if __name__ == "__main__":
    main()
