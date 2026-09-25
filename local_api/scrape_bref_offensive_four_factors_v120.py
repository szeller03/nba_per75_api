"""
NBA PER-75 — DIRECT B-REF OFFENSIVE FOUR FACTORS v120
Offline recovery from existing Basketball-Reference HTML cache.

Extracts ONLY:
  - offensive eFG%
  - offensive TOV%

Does NOT touch:
  - FTr
  - opponent eFG%
  - opponent TOV%
  - any other team metric

This script scans existing local B-Ref season-summary HTML files and writes:
  local_api/cache/bref_offensive_four_factors_v1.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from io import StringIO

import pandas as pd
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "local_api" / "cache"
OUT_CACHE = CACHE_DIR / "bref_offensive_four_factors_v1.json"

FIRST_YEAR = 1952
LAST_YEAR = 2026


def clean_text(value):
    return re.sub(r"\s+", " ", str(value)).strip()


def flatten_columns(columns):
    """Preserve the complete MultiIndex path so Offense/Defense columns
    cannot collapse into the same leaf name."""
    out = []
    for col in columns:
        if isinstance(col, tuple):
            parts = []
            for x in col:
                s = clean_text(x)
                if s and s.lower() != "nan" and s not in parts:
                    parts.append(s)
            out.append(" | ".join(parts))
        else:
            out.append(clean_text(col))
    return out


def numeric(value):
    if value is None:
        return None
    s = clean_text(value).replace("%", "")
    if not s or s.lower() in {"nan", "none", "na", "n/a"}:
        return None
    try:
        return float(s)
    except Exception:
        return None


def find_team_column(df):
    for c in df.columns:
        leaf = clean_text(c).lower()
        if leaf in {"team", "tm"} or leaf.endswith(" | team") or leaf.endswith(" | tm"):
            return c
    return None


def find_offensive_column(df, metric):
    metric = metric.lower()
    candidates = []
    for c in df.columns:
        s = clean_text(c).lower()
        if metric not in s:
            continue
        # Prefer columns explicitly under Offense / offensive headers.
        score = 0
        if "offense" in s or "offensive" in s:
            score += 10
        if "defense" in s or "defensive" in s or "opponent" in s:
            score -= 20
        if metric == "efg":
            if "efg%" in s or "efg" in s:
                score += 2
        elif metric == "tov":
            if "tov%" in s or "tov" in s:
                score += 2
        candidates.append((score, c))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[0], str(x[1])))
    return candidates[0][1]


def parse_tables(html):
    tables = []
    soup = BeautifulSoup(html, "html.parser")

    # Normal tables
    for table in soup.find_all("table"):
        try:
            dfs = pd.read_html(StringIO(str(table)))
            tables.extend(dfs)
        except Exception:
            pass

    # B-Ref commonly hides tables inside HTML comments.
    for comment in soup.find_all(string=lambda t: isinstance(t, type(soup.string))):
        pass

    from bs4 import Comment
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        if "<table" not in str(comment):
            continue
        try:
            dfs = pd.read_html(StringIO(str(comment)))
            tables.extend(dfs)
        except Exception:
            pass

    return tables


def extract_from_html(html):
    best = {}

    for df in parse_tables(html):
        if df is None or df.empty:
            continue

        df = df.copy()
        df.columns = flatten_columns(df.columns)

        team_col = find_team_column(df)
        efg_col = find_offensive_column(df, "efg")
        tov_col = find_offensive_column(df, "tov")

        if team_col is None or efg_col is None or tov_col is None:
            continue

        # Favor a table whose headers explicitly identify both metrics as
        # offensive and which has a reasonable number of team rows.
        for _, row in df.iterrows():
            team = clean_text(row.get(team_col, ""))
            if not team or team.lower() in {
                "team", "league average", "league", "average"
            }:
                continue

            # Remove repeated header rows.
            if team.lower() in {"tm", "rk", "nan"}:
                continue

            efg = numeric(row.get(efg_col))
            tov = numeric(row.get(tov_col))

            if efg is None or tov is None:
                continue

            # Team names can have footnote markers.
            team = re.sub(r"\s*\([^)]*\)\s*$", "", team).strip()

            best[team] = {
                "efgpct": efg / 100.0 if efg > 1 else efg,
                "tovpct": tov / 100.0 if tov > 1 else tov,
            }

    return best


def candidate_paths(year):
    names = [
        f"NBA_{year}.html",
        f"NBA_{year}.htm",
    ]

    roots = [
        ROOT,
        ROOT / "cache",
        ROOT / "local_api" / "cache",
        ROOT / "local_api" / "cache" / "bref",
        ROOT / "local_api" / "cache" / "bref_html",
        ROOT / "local_api" / "cache" / "basketball_reference",
        ROOT / "local_api" / "cache" / "bref_seasons",
    ]

    # Also recursively search likely cache directories if the direct
    # conventional locations do not contain the file.
    seen = set()
    paths = []
    for root in roots:
        if not root.exists():
            continue
        for name in names:
            p = root / name
            if p.exists() and p not in seen:
                paths.append(p)
                seen.add(p)

        try:
            for p in root.rglob(f"NBA_{year}.html"):
                if p not in seen:
                    paths.append(p)
                    seen.add(p)
        except Exception:
            pass

    return paths


def load_existing_cache():
    if not OUT_CACHE.exists():
        return {}
    try:
        with OUT_CACHE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cache(data):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_CACHE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    tmp.replace(OUT_CACHE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=FIRST_YEAR)
    ap.add_argument("--end", type=int, default=LAST_YEAR)
    args = ap.parse_args()

    cache = load_existing_cache()

    print("=" * 88)
    print("NBA PER-75 — OFFLINE B-REF OFFENSIVE FOUR FACTORS v120")
    print("=" * 88)
    print("Extracting ONLY: offensive eFG% and offensive TOV%")
    print("FTr: NOT TOUCHED")
    print("Opponent eFG% / TOV%: NOT TOUCHED")
    print(f"Season range: {args.start - 1}-{args.end - 1}")
    print(f"Existing cached season maps: {len(cache)}")
    print()

    recovered = 0
    total_rows = 0

    for year in range(args.start, args.end + 1):
        season = f"{year - 1}-{str(year)[-2:]}"
        key = f"{season}|Regular Season"

        paths = candidate_paths(year)
        if not paths:
            print(f"MISSING {key} — no local NBA_{year}.html found")
            continue

        found = False
        for path in paths:
            try:
                html = path.read_text(encoding="utf-8", errors="ignore")
                rows = extract_from_html(html)
            except Exception as exc:
                print(f"ERROR {key} — {path}: {exc}")
                continue

            if not rows:
                continue

            cache[key] = rows
            save_cache(cache)
            recovered += 1
            total_rows += len(rows)
            print(f"OK {key} — teams={len(rows)} — source={path}")
            found = True
            break

        if not found:
            print(f"NO FOUR-FACTOR TABLE {key}")

    save_cache(cache)

    print()
    print("=" * 88)
    print("RECOVERY COMPLETE")
    print("=" * 88)
    print(f"Season maps in cache: {len(cache)}")
    print(f"Newly recovered maps: {recovered}")
    print(f"Recovered team-season rows: {total_rows}")
    print(f"Cache: {OUT_CACHE}")
    print()
    print("No live Basketball-Reference requests were made.")


if __name__ == "__main__":
    main()
