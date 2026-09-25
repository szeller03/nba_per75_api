"""
NBA PER-75 — OFFLINE B-REF OFFENSIVE FOUR FACTORS v121

Imports the already-extracted Basketball-Reference offensive Four Factors
from the bundled CSV into the local API's B-Ref Four Factors cache.

ONLY imports:
  - offensive eFG%
  - offensive TOV%

DOES NOT modify:
  - FTr
  - opponent eFG%
  - opponent TOV%
  - any other metric
  - frontend/source files
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "local_api" / "cache"
CSV_PATH = CACHE_DIR / "bref_offensive_four_factors_v1.csv"
JSON_PATH = CACHE_DIR / "bref_team_four_factors_v3.json"


def clean_team(name: str) -> str:
    # Keep the canonical B-Ref team label. The API's team-key normalizer
    # handles franchise/star normalization downstream.
    return re.sub(r"\s+", " ", str(name)).strip()


def load_existing():
    if not JSON_PATH.exists():
        return {
            "extract_only": ["eFG%", "TOV%"],
            "ftr_touched": False,
            "seasons": {},
        }

    try:
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("cache is not a JSON object")
        data.setdefault("seasons", {})
        data.setdefault("extract_only", ["eFG%", "TOV%"])
        data["ftr_touched"] = False
        return data
    except Exception as exc:
        print(f"Existing cache could not be read; creating a fresh cache: {exc}")
        return {
            "extract_only": ["eFG%", "TOV%"],
            "ftr_touched": False,
            "seasons": {},
        }


def main():
    if not CSV_PATH.exists():
        raise SystemExit(f"Missing bundled source: {CSV_PATH}")

    data = load_existing()
    seasons = data["seasons"]

    imported_rows = 0
    imported_seasons = set()

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        required = {"season", "season_type", "team", "efgpct", "tovpct"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise SystemExit(
                f"CSV is missing required columns. Found: {reader.fieldnames}"
            )

        for row in reader:
            season = row["season"].strip()
            season_type = row["season_type"].strip()
            team = clean_team(row["team"])

            if not season or not season_type or not team:
                continue

            key = f"{season}|{season_type}"
            season_map = seasons.setdefault(key, {})

            # IMPORTANT: only these two fields are written.
            # Existing fields such as opponent factors remain untouched.
            entry = season_map.setdefault(team, {})

            entry["efgpct"] = float(row["efgpct"])
            entry["tovpct"] = float(row["tovpct"])

            imported_rows += 1
            imported_seasons.add(key)

    data["extract_only"] = ["eFG%", "TOV%"]
    data["ftr_touched"] = False

    tmp = JSON_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(JSON_PATH)

    print("=" * 88)
    print("NBA PER-75 — OFFLINE B-REF OFFENSIVE FOUR FACTORS v121")
    print("=" * 88)
    print("Imported ONLY: offensive eFG% and offensive TOV%")
    print("FTr: NOT TOUCHED")
    print("Opponent eFG% / TOV%: NOT TOUCHED")
    print(f"Imported team-season rows: {imported_rows}")
    print(f"Season maps containing imported data: {len(imported_seasons)}")
    print(f"Cache: {JSON_PATH}")
    print()
    print("No Basketball-Reference requests were made.")
    print("No frontend files were changed.")


if __name__ == "__main__":
    main()
