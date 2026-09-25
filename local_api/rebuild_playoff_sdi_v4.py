"""Rebuild the playoff SDI cache from the canonical playoff percentile layer.

IMPORTANT: This script never modifies any regular-season SDI file.  The playoff
formula is the locked regular-season SDI v4 formula projected into playoffs:
- retain Scoring Volume, Scoring Efficiency, Creation & Playmaking, Rebounding
- remove Defense and Impact / Value completely
- remove WOWY Offense from Creation & Playmaking and proportionally renormalize
  the remaining Creation groups (.385/.315 -> .55/.45)
- percentile every resulting category score against the appropriate playoff
  population; the Player Profile consumes those category percentiles.
"""
from pathlib import Path
import sys
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local_api"))
import nba_per75_local_api as api

OUT = ROOT / "local_api" / "cache" / "playoff_sdi_v4_player_seasons.csv"


def main():
    # The authoritative builder now derives its specification from the locked
    # regular-season formula representation inside the API.  No regular cache
    # is opened for writing.
    d = api._build_playoff_sdi_v4_index()
    if d is None or d.empty:
        raise RuntimeError(
            "Canonical playoff percentile/statistic layer is unavailable; "
            "playoff SDI cache was not changed."
        )

    # Keep the cache schema useful to existing consumers while exposing the
    # four category scores explicitly. These are RAW SDI category scores; the
    # Player Profile displays their separately ranked percentiles.
    rename = {
        "SDI_Scoring_Volume": "SDI_scoring_volume",
        "SDI_Scoring_Efficiency": "SDI_scoring_efficiency",
        "SDI_Creation_and_Playmaking": "SDI_creation_playmaking",
        "SDI_Creation___Playmaking": "SDI_creation_playmaking",
        "SDI_Rebounding": "SDI_rebounding",
    }
    for a, b in list(rename.items()):
        if a in d.columns and b not in d.columns:
            d = d.rename(columns={a: b})

    keep = [
        "Player_ID", "Player", "SeasonEndYear", "G", "MP", "SDI_v4",
        "SDI_scoring_volume", "SDI_scoring_efficiency",
        "SDI_creation_playmaking", "SDI_rebounding",
    ]
    keep = [c for c in keep if c in d.columns]
    out = d[keep].copy()
    out["Season"] = out["SeasonEndYear"].map(api._season_label_any)
    out = out.sort_values(["SeasonEndYear", "Player"], kind="stable")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)

    print("PLAYOFF SDI CACHE REBUILT")
    print(f"Rows: {len(out):,}")
    print(f"Output: {OUT}")
    print("Regular-season SDI files: NOT MODIFIED")


if __name__ == "__main__":
    main()
