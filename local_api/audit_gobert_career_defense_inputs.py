"""Audit Rudy Gobert's Career Defense SDI inputs.

Does NOT modify any site data. It reports:
- Gobert's underlying career values
- Career percentile for every Defense input
- Gobert's rank and population size for each input
- Defensive Activity, Defensive Activity Rate, WOWY Defense and final Defense
- Exact weighted-math reconstruction
- Availability/coverage warnings
- A comparison against the authoritative Career SDI row

Usage from Website241 root:
  python local_api/audit_gobert_career_defense_inputs.py
"""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local_api"))
import nba_per75_local_api as api

LOWER_IS_BETTER = {"TOV_per75", "TOV_pct", "PF_per75", "DRtg", "Relative_DRtg"}
DEFENSE = {
    "Defensive Activity": {"weight": 0.35, "statistics": {"STL_per75": 0.40, "BLK_per75": 0.60}},
    "Defensive Activity Rate": {"weight": 0.25, "statistics": {"STL_pct": 0.40, "BLK_pct": 0.60}},
    "WOWY Defensive Impact": {"weight": 0.40, "statistics": {"WOWY_Defense": 1.00}},
}

def col(df, candidates):
    lookup = {str(c).strip().casefold(): c for c in df.columns}
    for x in candidates:
        if str(x).strip().casefold() in lookup:
            return lookup[str(x).strip().casefold()]
    return None

def norm_name(s):
    return str(s).replace("*", "").strip().casefold()

def percentile_detail(series, value, higher=True):
    """Return a true population percentile for one target value.

    Important: the target rank is taken from the FULL valid population.
    Never rank the one matching target value by itself (which would make
    every unique player look like rank 1 / 100th percentile).
    """
    s = pd.to_numeric(series, errors="coerce")
    valid = s.dropna()
    direction = "higher" if higher else "lower"
    if valid.empty or pd.isna(value):
        return {"percentile": None, "rank": None, "n": int(len(valid)), "better_direction": direction}

    value = float(value)
    n = int(len(valid))
    ranks = valid.rank(method="average", ascending=not higher)

    # Find the target's rank inside the COMPLETE population.  Use a small
    # tolerance for floating-point representation differences.
    mask = np.isclose(valid.to_numpy(dtype=float), value, rtol=1e-10, atol=1e-10)
    if mask.any():
        target_rank = float(ranks.iloc[np.flatnonzero(mask)].mean())
    else:
        # The target should normally be present in the population. If not,
        # insert its rank by counting strictly better observations and then
        # accounting for ties at the nearest representable value.
        if higher:
            target_rank = float(1 + (valid > value).sum())
        else:
            target_rank = float(1 + (valid < value).sum())

    # Higher is better: best rank (1) = 100.
    # Lower is better: smallest value gets rank 1 = 100.
    pct = 100.0 if n == 1 else 100.0 * (n - target_rank) / (n - 1)

    if higher:
        better = int((valid >= value).sum())
        cutoff = float(valid.quantile(0.90))
    else:
        better = int((valid <= value).sum())
        cutoff = float(valid.quantile(0.10))

    return {
        "percentile": float(pct),
        "rank": float(target_rank),
        "n": n,
        "better_direction": direction,
        "players_at_or_better": better,
        "top_10_percent_cutoff": cutoff,
        "median": float(valid.median()),
        "min": float(valid.min()),
        "max": float(valid.max()),
    }

def main():
    career = api._build_regular_career_table().copy()
    if career.empty:
        raise RuntimeError("Canonical career table is empty.")

    # Reuse the exact WOWY reconstruction used by the validated 50.7.1 build.
    try:
        from audit_career_sdi_v2 import build_career_wowy
        career, wowy_meta = build_career_wowy(career)
    except Exception as exc:
        raise RuntimeError(f"Could not reconstruct canonical Career WOWY: {exc}") from exc

    target = career.loc[career["Player"].map(norm_name).eq("rudy gobert")]
    if target.empty:
        raise RuntimeError("Rudy Gobert not found in canonical Career table.")
    t = target.iloc[0]

    g = pd.to_numeric(career.get("G", np.nan), errors="coerce")
    mp = pd.to_numeric(career.get("MP", np.nan), errors="coerce")
    qualified = career.loc[g.ge(400) & mp.ge(10000)].copy()
    if qualified.empty:
        raise RuntimeError("No qualified career population.")

    stats = ["STL_per75", "BLK_per75", "STL_pct", "BLK_pct", "WOWY_Defense"]
    inputs = {}
    for stat in stats:
        if stat not in qualified.columns:
            inputs[stat] = {"error": "missing column"}
            continue
        val = pd.to_numeric(pd.Series([t.get(stat, np.nan)]), errors="coerce").iloc[0]
        # All five Defense inputs are higher-is-better.
        inputs[stat] = {
            "value": None if pd.isna(val) else float(val),
            **percentile_detail(qualified[stat], val, higher=True),
        }

    activity = 0.40 * inputs["STL_per75"]["percentile"] + 0.60 * inputs["BLK_per75"]["percentile"]
    activity_rate = 0.40 * inputs["STL_pct"]["percentile"] + 0.60 * inputs["BLK_pct"]["percentile"]
    wowy = inputs["WOWY_Defense"].get("percentile")
    defense = activity * .35 + activity_rate * .25 + wowy * .40

    # Read the actual rebuilt Career SDI row for direct comparison.
    output_path = ROOT / "data" / "regular_career_sdi_v4_wowy_rts.csv"
    rebuilt = pd.read_csv(output_path, low_memory=False) if output_path.exists() else pd.DataFrame()
    actual = None
    if not rebuilt.empty:
        hit = rebuilt.loc[rebuilt["Player"].map(norm_name).eq("rudy gobert")]
        if not hit.empty:
            r = hit.iloc[0]
            actual = {k: (None if pd.isna(r.get(k)) else float(r.get(k))) for k in ["Career_defense", "WOWY_Defense"]}

    # Coverage warnings for each input across the qualified population.
    coverage = {s: float(pd.to_numeric(qualified[s], errors="coerce").notna().mean()) if s in qualified.columns else 0.0 for s in stats}

    report = {
        "version": "Career_Defense_Input_Audit_v1",
        "player": "Rudy Gobert",
        "player_id": str(t.get("Player_ID", "")),
        "career_games": None if pd.isna(g.loc[t.name]) else float(g.loc[t.name]),
        "career_minutes": None if pd.isna(mp.loc[t.name]) else float(mp.loc[t.name]),
        "qualified_career_population": int(len(qualified)),
        "wowy_reconstruction": wowy_meta,
        "inputs": inputs,
        "defensive_activity": float(activity),
        "defensive_activity_rate": float(activity_rate),
        "wowy_defensive_impact": float(wowy),
        "reconstructed_defense": float(defense),
        "weights": {"activity": .35, "activity_rate": .25, "wowy_defense": .40},
        "qualified_population_coverage": coverage,
        "rebuilt_csv_value": actual,
        "diagnosis": "",
    }

    if actual and actual.get("Career_defense") is not None and abs(actual["Career_defense"] - defense) < 1e-7:
        report["diagnosis"] = "MATH_MATCHES_REBUILT_CSV"
    else:
        report["diagnosis"] = "REBUILT_CSV_MISMATCH"

    out = ROOT / "data" / "GOBERT_CAREER_DEFENSE_INPUT_AUDIT.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
