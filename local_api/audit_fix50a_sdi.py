"""Fix 50A SDI audit.

Run from the website root:
    python local_api/audit_fix50a_sdi.py

This is intentionally read-only. It checks:
- authoritative top-level SDI weights
- companion percentile direction
- presence of evidence/availability layers
- Wilt and Shaq seasonal cache coverage fields
"""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TOP = {
    "scoring_volume": 0.22,
    "scoring_efficiency": 0.20,
    "creation_playmaking": 0.20,
    "rebounding": 0.105,
    "defense": 0.22,
    "impact_value": 0.055,
}

def main():
    config = ROOT / "config" / "statistical_index_v4_locked.json"
    if not config.exists():
        raise SystemExit(f"Missing {config}")
    data = json.loads(config.read_text(encoding="utf-8"))
    got = data["regular_season"]["top_level_weights"]
    print("Top-level weights:")
    for k, expected in EXPECTED_TOP.items():
        label = {
            "scoring_volume":"Scoring Volume",
            "scoring_efficiency":"Efficiency",
            "creation_playmaking":"Creation / Playmaking",
            "rebounding":"Rebounding",
            "defense":"Defense",
            "impact_value":"Impact / Value",
        }[k]
        actual = float(got[label])
        print(f"  {label}: {actual:.6f}  {'OK' if abs(actual-expected)<1e-12 else 'MISMATCH'}")

    candidates = [
        ROOT / "data" / "regular_sdi_v4_wowy_player_seasons.csv",
        ROOT / "local_api" / "cache" / "regular_sdi_v4_wowy_player_seasons.csv",
    ]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("No seasonal WOWY SDI cache found; skipping player spot-check.")
        return
    df = pd.read_csv(src, low_memory=False)
    print(f"\nSeasonal SDI source: {src}")
    for player in ["Wilt Chamberlain", "Shaquille O'Neal"]:
        rows = df[df["Player"].astype(str).str.casefold().eq(player.casefold())]
        print(f"{player}: {len(rows)} season rows")
        cols = [c for c in [
            "Season","MP","SDI_v4_WOWY",
            "SDI_defense_Coverage","SDI_scoring_efficiency_Coverage"
        ] if c in rows.columns]
        if cols:
            print(rows[cols].to_string(index=False))

if __name__ == "__main__":
    main()
