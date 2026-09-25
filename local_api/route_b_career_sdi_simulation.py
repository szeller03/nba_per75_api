#!/usr/bin/env python3
"""
ROUTE B CAREER SDI SIMULATION — NO PRODUCTION CHANGES

Purpose
-------
Take the existing Career SDI category composites and calculate a second,
viewer-facing percentile layer:

    existing weighted category score
        -> percentile rank of that score across the qualified population

This does NOT alter the site's production CSVs.

Expected input:
    data/regular_career_sdi_v4_wowy_rts.csv

Fallback locations:
    local_api/data/regular_career_sdi_v4_wowy_rts.csv
    local_api/cache/regular_career_sdi_v4_wowy_rts.csv

Output:
    route_b_career_sdi_comparison.csv
    route_b_career_sdi_top25_by_category.csv
    route_b_career_sdi_named_players.csv
"""

from __future__ import annotations
from pathlib import Path
import sys
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = [
    ROOT / "data" / "regular_career_sdi_v4_wowy_rts.csv",
    ROOT / "local_api" / "data" / "regular_career_sdi_v4_wowy_rts.csv",
    ROOT / "local_api" / "cache" / "regular_career_sdi_v4_wowy_rts.csv",
    Path(__file__).resolve().parent / "regular_career_sdi_v4_wowy_rts.csv",
]

CATEGORIES = {
    "Scoring": "Career_scoring_volume",
    "Efficiency": "Career_scoring_efficiency",
    "Creation": "Career_creation_playmaking",
    "Rebounding": "Career_rebounding",
    "Defense": "Career_defense",
    "Impact": "Career_impact_value",
    "Overall SDI": "Career_SDI_v4",
}

NAMED = [
    "Hakeem Olajuwon",
    "Ben Wallace",
    "David Robinson",
    "Bill Russell",
    "Draymond Green",
    "Kevin Garnett",
    "Scottie Pippen",
    "Wilt Chamberlain",
    "Patrick Ewing",
    "Kareem Abdul-Jabbar",
    "Tim Duncan",
    "Rudy Gobert",
    "Alonzo Mourning",
    "Dikembe Mutombo",
    "Dennis Rodman",
    "Michael Jordan",
    "LeBron James",
    "Shaquille O'Neal",
    "Kobe Bryant",
    "Stephen Curry",
]

def find_input():
    for p in CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Could not find regular_career_sdi_v4_wowy_rts.csv. "
        "Expected it in data/, local_api/data/, or local_api/cache/."
    )

def percentile(values: pd.Series) -> pd.Series:
    """Higher composite score = better. Max score receives 100."""
    x = pd.to_numeric(values, errors="coerce")
    valid = x.notna()
    out = pd.Series(np.nan, index=x.index, dtype=float)
    if valid.sum() == 0:
        return out
    ranks = x[valid].rank(method="average", ascending=True)
    n = len(ranks)
    if n == 1:
        out.loc[valid] = 100.0
    else:
        out.loc[valid] = 100.0 * (ranks - 1.0) / (n - 1.0)
    return out

def normalize_name(s):
    return (
        s.astype(str)
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "", regex=True)
    )

def main():
    src = find_input()
    df = pd.read_csv(src)

    required = ["Player_ID", "Player", "Qualified_Career"] + list(CATEGORIES.values())
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Match the production qualified population.
    q = df[df["Qualified_Career"].astype(str).str.lower().isin(
        {"true", "1", "yes"}
    )].copy()

    # Some builds may store booleans as actual bools.
    if q.empty:
        q = df[df["Qualified_Career"].eq(True)].copy()

    if q.empty:
        raise ValueError("No Qualified_Career=True rows found.")

    result = q[["Player_ID", "Player", "Career_G", "Career_MP", "Qualified_Career"]].copy()

    for label, col in CATEGORIES.items():
        result[f"Current_{label.replace(' ', '_')}"] = pd.to_numeric(q[col], errors="coerce")
        result[f"RouteB_{label.replace(' ', '_')}"] = percentile(q[col])

    # Also report the percentile shift.
    for label in CATEGORIES:
        a = result[f"Current_{label.replace(' ', '_')}"]
        b = result[f"RouteB_{label.replace(' ', '_')}"]
        result[f"RouteB_Shift_{label.replace(' ', '_')}"] = b - a

    result = result.sort_values("Player").reset_index(drop=True)

    # Top 25 under Route B for each category.
    top_frames = []
    for label in CATEGORIES:
        col = f"RouteB_{label.replace(' ', '_')}"
        x = result[result[col].notna()].nlargest(25, col).copy()
        x.insert(0, "Category", label)
        x.insert(1, "RouteB_Rank", range(1, len(x) + 1))
        top_frames.append(
            x[[
                "Category", "RouteB_Rank", "Player_ID", "Player",
                f"Current_{label.replace(' ', '_')}", col
            ]]
        )
    top25 = pd.concat(top_frames, ignore_index=True)

    # Named-player side-by-side view.
    name_key = normalize_name(result["Player"])
    wanted = {normalize_name(pd.Series([n])).iloc[0]: n for n in NAMED}
    named = result[name_key.isin(wanted.keys())].copy()
    named["Requested_Name"] = name_key.loc[named.index].map(wanted)
    named = named.sort_values("Requested_Name")

    # Write outputs beside this script.
    outdir = Path(__file__).resolve().parent
    result_path = outdir / "route_b_career_sdi_comparison.csv"
    top_path = outdir / "route_b_career_sdi_top25_by_category.csv"
    named_path = outdir / "route_b_career_sdi_named_players.csv"

    result.to_csv(result_path, index=False)
    top25.to_csv(top_path, index=False)
    named.to_csv(named_path, index=False)

    print("=" * 72)
    print("ROUTE B CAREER SDI SIMULATION")
    print("=" * 72)
    print(f"Input: {src}")
    print(f"Qualified population: {len(q):,}")
    print()
    print("Named-player comparison:")
    display_cols = ["Player"]
    for label in CATEGORIES:
        k = label.replace(" ", "_")
        display_cols += [f"Current_{k}", f"RouteB_{k}"]
    print(named[display_cols].to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    print()
    print("Route B leaders:")
    for label in CATEGORIES:
        k = label.replace(" ", "_")
        row = result.loc[result[f"RouteB_{k}"].idxmax()]
        print(
            f"{label:12s}: {row['Player']} "
            f"(current {row[f'Current_{k}']:.2f} -> Route B {row[f'RouteB_{k}']:.2f})"
        )
    print()
    print("Files written:")
    print(f"  {result_path}")
    print(f"  {top_path}")
    print(f"  {named_path}")

if __name__ == "__main__":
    main()
