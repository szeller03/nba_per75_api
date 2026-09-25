"""
NBA PER-75 — BASKETBALL-REFERENCE PLAYOFF SOURCE BUILDER V1

Canonical playoff raw source:
    Basketball-Reference playoff player totals pages
    https://www.basketball-reference.com/playoffs/NBA_YYYY_totals.html

Coverage:
    1952 through the requested ending season.

Output:
    C:\\Users\\szell\\OneDrive\\Desktop\\NBA_Per75\\data\\nba_per75_playoffs_bref_v1.csv

The output is a RAW source layer only. It does not calculate PER-75,
percentiles, qualification, spiders, or career values.

The builder deliberately preserves unavailable historical statistics as blank
values. It never converts a missing historical statistic into zero.
"""

from __future__ import annotations

import argparse
import io
import re
import time
from pathlib import Path
from html.parser import HTMLParser

import pandas as pd
import requests

ROOT = Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75")
OUT = ROOT / "data" / "nba_per75_playoffs_bref_v1.csv"
AUDIT = ROOT / "data" / "nba_per75_playoffs_bref_build_audit_v1.csv"

BASE_URL = "https://www.basketball-reference.com/playoffs/NBA_{year}_totals.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

CANONICAL_COLUMNS = [
    "Season", "Season_Type", "Player", "Player_ID", "Team",
    "G", "GS", "MP", "FG", "FGA", "FG%", "3P", "3PA", "3P%",
    "2P", "2PA", "2P%", "eFG%", "FT", "FTA", "FT%",
    "ORB", "DRB", "TRB", "AST", "STL", "BLK", "TOV", "PF", "PTS",
]

RENAME = {
    "Player": "Player",
    "Tm": "Team",
    "G": "G",
    "GS": "GS",
    "MP": "MP",
    "FG": "FG",
    "FGA": "FGA",
    "FG%": "FG%",
    "3P": "3P",
    "3PA": "3PA",
    "3P%": "3P%",
    "2P": "2P",
    "2PA": "2PA",
    "2P%": "2P%",
    "eFG%": "eFG%",
    "FT": "FT",
    "FTA": "FTA",
    "FT%": "FT%",
    "ORB": "ORB",
    "DRB": "DRB",
    "TRB": "TRB",
    "AST": "AST",
    "STL": "STL",
    "BLK": "BLK",
    "TOV": "TOV",
    "PF": "PF",
    "PTS": "PTS",
}

class CommentExtractor(HTMLParser):
    """Extract HTML comments because B-Ref commonly wraps tables in comments."""
    def __init__(self):
        super().__init__()
        self.comments = []

    def handle_comment(self, data):
        self.comments.append(data)

def season_years(start_year: int, end_year: int):
    return list(range(start_year, end_year + 1))

def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        cols = []
        for c in df.columns:
            parts = [str(x).strip() for x in c if str(x).strip() not in ("", "nan")]
            cols.append(parts[-1] if parts else "")
        df.columns = cols
    else:
        df.columns = [str(c).strip() for c in df.columns]
    return df

def get_player_totals_table(html: str) -> pd.DataFrame:
    # First try normal HTML.
    tables = []
    try:
        tables.extend(pd.read_html(io.StringIO(html)))
    except ValueError:
        pass

    # Then inspect comments, where Basketball-Reference frequently stores
    # its tables in the raw page.
    if not any({"Player", "Tm"}.issubset(set(map(str, t.columns))) for t in tables):
        parser = CommentExtractor()
        parser.feed(html)
        for comment in parser.comments:
            if "Player Totals" in comment or "totals_stats" in comment:
                try:
                    tables.extend(pd.read_html(io.StringIO(comment)))
                except (ValueError, TypeError):
                    continue

    for table in tables:
        table = flatten_columns(table)
        cols = set(map(str, table.columns))
        if "Player" in cols and "Tm" in cols and "PTS" in cols:
            # Prefer the actual player totals table, not team totals.
            if "Rk" in cols and ("G" in cols or "MP" in cols):
                return table

    raise ValueError("Could not locate Basketball-Reference Player Totals table.")

def clean_player_name(value):
    s = str(value).strip()
    if s in ("nan", "None", ""):
        return ""
    # B-Ref may include an asterisk for award/historical markers.
    return re.sub(r"\*$", "", s).strip()

def fetch_year(session: requests.Session, year: int) -> pd.DataFrame:
    url = BASE_URL.format(year=year)
    response = session.get(url, headers=HEADERS, timeout=45)
    response.raise_for_status()

    table = get_player_totals_table(response.text)
    table = table.rename(columns=RENAME)

    # Remove repeated header rows and non-player rows.
    if "Player" not in table.columns:
        raise ValueError("Player column missing after normalization.")

    table["Player"] = table["Player"].map(clean_player_name)
    table = table.loc[
        table["Player"].ne("") &
        ~table["Player"].str.casefold().isin(
            {"player", "league average", "team totals"}
        )
    ].copy()

    # B-Ref can list a player multiple times for traded teams. Keep every
    # team row in the raw source; later analytical layers can consolidate.
    table.insert(0, "Season", year)
    table.insert(1, "Season_Type", "Playoffs")

    # Normalize only the fields we actually know how to map.
    if "Player" in table.columns:
        table["Player"] = table["Player"].astype(str).str.strip()
    for col in table.columns:
        if col not in ("Season", "Season_Type", "Player", "Team"):
            table[col] = pd.to_numeric(table[col], errors="coerce")

    # B-Ref does not expose a universal player ID in this table, so leave the
    # identity field blank rather than guessing an ID.
    table.insert(3, "Player_ID", pd.NA)

    ordered = [c for c in CANONICAL_COLUMNS if c in table.columns]
    return table[ordered].copy()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1952)
    parser.add_argument("--end", type=int, default=2026)
    parser.add_argument("--delay", type=float, default=3.0)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    if args.start < 1952:
        raise ValueError("Basketball-Reference playoff source begins at 1952.")
    if args.end < args.start:
        raise ValueError("--end must be >= --start.")

    years = season_years(args.start, args.end)
    session = requests.Session()
    frames = []
    audit = []

    print("=" * 88)
    print("NBA PER-75 — BASKETBALL-REFERENCE PLAYOFF SOURCE BUILDER V1")
    print("=" * 88)
    print(f"Source: {BASE_URL}")
    print(f"Coverage requested: {args.start} through {args.end} ({len(years)} seasons)")
    print("Raw totals only. No PER-75/percentile calculations are performed here.")
    print()

    for i, year in enumerate(years, 1):
        success = False
        last_error = None

        for attempt in range(1, args.retries + 1):
            try:
                df = fetch_year(session, year)
                frames.append(df)
                audit.append({
                    "Season": year,
                    "Status": "Retrieved",
                    "Rows": len(df),
                    "Source": "Basketball-Reference",
                    "URL": BASE_URL.format(year=year),
                    "Error": None,
                })
                print(f"{i:>3}/{len(years)}  {year}: {len(df):,} player-team rows")
                success = True
                break
            except Exception as exc:
                last_error = str(exc)
                if attempt < args.retries:
                    time.sleep(max(args.delay, 5.0))
                else:
                    audit.append({
                        "Season": year,
                        "Status": "Failed",
                        "Rows": 0,
                        "Source": "Basketball-Reference",
                        "URL": BASE_URL.format(year=year),
                        "Error": last_error[:1000],
                    })
                    print(f"{i:>3}/{len(years)}  {year}: FAILED — {last_error[:180]}")

        if success:
            time.sleep(args.delay)

    OUT.parent.mkdir(parents=True, exist_ok=True)

    if frames:
        out = pd.concat(frames, ignore_index=True)

        # Explicitly preserve missing historical statistics as NaN.
        out.to_csv(OUT, index=False)

        print()
        print("=" * 88)
        print("BUILD COMPLETE")
        print("=" * 88)
        print(f"Seasons requested:       {len(years)}")
        print(f"Seasons retrieved:       {sum(a['Status']=='Retrieved' for a in audit)}")
        print(f"Seasons failed:          {sum(a['Status']=='Failed' for a in audit)}")
        print(f"Total raw rows:          {len(out):,}")
        print(f"Output:                  {OUT}")
    else:
        print("No playoff seasons were retrieved; no source CSV was created.")

    pd.DataFrame(audit).to_csv(AUDIT, index=False)
    print(f"Audit:                    {AUDIT}")

if __name__ == "__main__":
    main()
