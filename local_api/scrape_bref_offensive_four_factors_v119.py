#!/usr/bin/env python3
"""
NBA PER-75 — DIRECT BASKETBALL-REFERENCE OFFENSIVE FOUR FACTORS SCRAPER

Purpose
-------
Extract ONLY the offensive:
    eFG%
    TOV%

from Basketball-Reference's season summary Team Advanced/Four Factors data.

FTr is intentionally NOT scraped or changed by this tool.

Important
---------
- Direct Basketball-Reference source only.
- Does NOT use nba_per75_team_master.csv.
- Does NOT use nba_team_master.csv.
- Does NOT calculate offensive eFG% or TOV% from reconstructed formulas.
- Uses the same proven request/cache/table-parsing architecture as the
  original historical PER-75 scraper.
- Never sleeps for a server-provided Retry-After value.
- Existing completed cache entries are preserved.
- HTTP 403/429 stops the run; it does not attempt to bypass the block.
- Ordinary request errors get the original bounded retry behavior.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import re
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup, Comment


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "local_api" / "cache"

HTML_CACHE_DIR = CACHE_DIR / "bref_team_four_factors_html_v1"
JSON_CACHE = CACHE_DIR / "bref_team_four_factors_v3.json"

FIRST_YEAR = 1952
LAST_YEAR = 2026

MIN_DELAY = 10.0
MAX_DELAY = 15.0
REQUEST_TIMEOUT = 30
MAX_RETRIES = 2

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

class ScraperBlocked(Exception):
    pass


def season_label(year: int) -> str:
    return f"{year - 1}-{str(year)[-2:]}"


def polite_sleep() -> None:
    delay = random.uniform(MIN_DELAY, MAX_DELAY)
    print(f"    Waiting {delay:.1f} seconds...")
    time.sleep(delay)


def cache_filename(url: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", url)
    return HTML_CACHE_DIR / f"{safe}.html"


def repair_mojibake(text: str) -> str:
    if not text:
        return text
    markers = ("Ã", "Â", "Ä", "Å", "Æ", "Ð", "Ñ", "Ø", "Þ", "â")
    before = sum(text.count(x) for x in markers)
    if before == 0:
        return text
    try:
        repaired = text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    after = sum(repaired.count(x) for x in markers)
    return repaired if after < before else text


def fetch_html(session: requests.Session, url: str) -> Optional[str]:
    HTML_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = cache_filename(url)

    if cache_file.exists() and cache_file.stat().st_size > 500:
        print(f"    Using cached page: {cache_file.name}")
        html = cache_file.read_text(encoding="utf-8", errors="replace")
        html = repair_mojibake(html)
        return html

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"    Requesting: {url}")
        try:
            response = session.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            print(f"    Request error: {exc}")
            if attempt < MAX_RETRIES:
                polite_sleep()
                continue
            return None

        if response.status_code == 403:
            raise ScraperBlocked("Basketball-Reference returned HTTP 403.")

        if response.status_code == 429:
            # Deliberately do NOT read or sleep for Retry-After.
            raise ScraperBlocked("Basketball-Reference returned HTTP 429.")

        if response.status_code == 404:
            print("    Page does not exist.")
            return None

        if response.status_code != 200:
            print(f"    HTTP {response.status_code}")
            if attempt < MAX_RETRIES:
                polite_sleep()
                continue
            return None

        html = response.content.decode("utf-8", errors="replace")
        html = repair_mojibake(html)

        cache_file.write_text(html, encoding="utf-8")
        polite_sleep()
        return html

    return None


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        new_columns = []
        for column in df.columns:
            parts = [
                str(x).strip()
                for x in column
                if str(x).strip().lower() != "nan"
                and str(x).strip() != ""
            ]
            # Preserve the full path when duplicate leaf names exist.
            # This prevents an offensive eFG% from being silently replaced
            # by an opponent eFG% during MultiIndex flattening.
            if len(parts) > 1:
                new_columns.append(" | ".join(parts))
            else:
                new_columns.append(parts[0] if parts else "")
        df.columns = new_columns
    else:
        df.columns = [str(x).strip() for x in df.columns]

    return df


def read_all_tables(html: str) -> list[pd.DataFrame]:
    tables: list[pd.DataFrame] = []

    try:
        tables.extend(pd.read_html(io.StringIO(html)))
    except (ValueError, ImportError):
        pass

    soup = BeautifulSoup(html, "html.parser")
    comments = soup.find_all(
        string=lambda text: isinstance(text, Comment)
    )

    for comment in comments:
        text = str(comment)
        if "<table" not in text.lower():
            continue
        try:
            tables.extend(pd.read_html(io.StringIO(text)))
        except (ValueError, ImportError):
            continue

    return tables


def normalize_team_column(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = flatten_columns(df)

    aliases = {}
    for c in df.columns:
        low = str(c).strip().lower()
        if low in {"tm", "team", "team | tm"}:
            aliases[c] = "Team"

    if aliases:
        df = df.rename(columns=aliases)

    return df


def numeric_value(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace("%", "")
        if value == "" or value.lower() in {"nan", "none", "na", "n/a"}:
            return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if pd.notna(x) else None


def canonical_team_key(name: str) -> str:
    s = str(name).strip().upper()
    s = re.sub(r"\s+", " ", s)

    # Historical B-Ref team abbreviations used by the existing API/cache.
    aliases = {
        "PHL": "PHI",
        "SFW": "GSW",
        "KCK": "SAC",
        "CIN": "SAC",
        "SDC": "LAC",
        "SD": "LAC",
        "VAN": "MEM",
        "SEA": "OKC",
        "NJN": "BKN",
        "NJO": "BKN",
        "CHA": "CHA",
        "CHH": "CHA",
        "NOH": "NOP",
        "NOK": "NOP",
    }
    return aliases.get(s, s)


def find_team_advanced_table(tables: list[pd.DataFrame]) -> pd.DataFrame:
    candidates = []

    for original in tables:
        table = normalize_team_column(original)
        cols = list(table.columns)
        low = {str(c).lower(): c for c in cols}

        # We specifically need the offensive Four Factors columns.
        has_team = "team" in low
        has_efg = any(
            str(c).strip().lower() in {"efg%", "e_fg%", "e fg%"}
            for c in cols
        )
        has_tov = any(
            str(c).strip().lower() in {"tov%", "to%", "tov %"}
            for c in cols
        )

        if not (has_team and has_efg and has_tov):
            continue

        score = 0
        score += 10
        score += 3 if "ortg" in low else 0
        score += 3 if "drtg" in low else 0
        score += 2 if "pace" in low else 0
        score += 2 if "ts%" in low else 0
        score += 2 if "ftr" in low else 0
        score += 1 if "orb%" in low else 0

        candidates.append((score, table))

    if not candidates:
        raise ValueError(
            "Could not locate a B-Ref team table containing Team + eFG% + TOV%."
        )

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1].copy()


def choose_column(df: pd.DataFrame, aliases: set[str]) -> Optional[str]:
    for c in df.columns:
        if str(c).strip().lower() in aliases:
            return c
    return None


def extract_offensive_four_factors(html: str, year: int) -> dict[str, dict[str, float]]:
    tables = read_all_tables(html)
    table = find_team_advanced_table(tables)

    team_col = choose_column(table, {"team", "tm"})
    efg_col = choose_column(table, {"efg%", "e_fg%", "e fg%"})
    tov_col = choose_column(table, {"tov%", "to%", "tov %"})

    if not team_col or not efg_col or not tov_col:
        raise ValueError(
            f"{season_label(year)}: required offensive eFG%/TOV% columns not found."
        )

    result = {}

    for _, row in table.iterrows():
        team_name = str(row.get(team_col, "")).strip()
        if not team_name:
            continue

        low = team_name.lower()
        if low in {"league average", "league", "average", "nan"}:
            continue

        efg = numeric_value(row.get(efg_col))
        tov = numeric_value(row.get(tov_col))

        if efg is None or tov is None:
            continue

        # B-Ref percentage fields are stored as percentage values:
        # e.g. .509 is displayed as 50.9, not .509.
        # Keep the source's percentage representation exactly as extracted.
        result[canonical_team_key(team_name)] = {
            "efgpct": float(efg),
            "tovpct": float(tov),
        }

    if not result:
        raise ValueError(f"{season_label(year)}: no team Four Factors rows extracted.")

    return result


def load_cache() -> dict:
    if not JSON_CACHE.exists():
        return {
            "version": "v3-direct-offensive-only",
            "seasons": {},
        }

    try:
        data = json.loads(JSON_CACHE.read_text(encoding="utf-8"))
    except Exception:
        print("Existing Four Factors cache could not be read; starting a new v3 cache.")
        return {
            "version": "v3-direct-offensive-only",
            "seasons": {},
        }

    if not isinstance(data, dict):
        return {
            "version": "v3-direct-offensive-only",
            "seasons": {},
        }

    data.setdefault("seasons", {})
    data["version"] = "v3-direct-offensive-only"
    return data


def save_cache(data: dict) -> None:
    JSON_CACHE.parent.mkdir(parents=True, exist_ok=True)
    temp = JSON_CACHE.with_suffix(".tmp")
    temp.write_text(
        json.dumps(data, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp.replace(JSON_CACHE)


def season_key(year: int, season_type: str = "Regular Season") -> str:
    return f"{season_label(year)}|{season_type}"


def main() -> None:
    global MIN_DELAY, MAX_DELAY
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=FIRST_YEAR)
    parser.add_argument("--end", type=int, default=LAST_YEAR)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--min-delay", type=float, default=MIN_DELAY)
    parser.add_argument("--max-delay", type=float, default=MAX_DELAY)
    args = parser.parse_args()

    MIN_DELAY = args.min_delay
    MAX_DELAY = args.max_delay

    if args.start > args.end:
        raise SystemExit("--start must be <= --end")

    data = load_cache()
    seasons = data["seasons"]

    print("=" * 88)
    print("NBA PER-75 — DIRECT B-REF OFFENSIVE FOUR FACTORS")
    print("=" * 88)
    print("Source: Basketball-Reference season summary Team Advanced/Four Factors")
    print("Extracting ONLY: offensive eFG% and offensive TOV%")
    print("FTr: NOT touched")
    print("No CSV Four Factors source is used.")
    print(f"Season range: {season_label(args.start)} through {season_label(args.end)}")
    print(f"Existing completed season maps: {len(seasons)}")
    print()

    session = requests.Session()

    for year in range(args.start, args.end + 1):
        key = season_key(year)

        if key in seasons and not args.refresh:
            teams = seasons[key].get("teams", {})
            print(f"SKIP {key} — cached teams={len(teams)}")
            continue

        url = f"https://www.basketball-reference.com/leagues/NBA_{year}.html"
        print(f"\n=== {key} ===")

        try:
            html = fetch_html(session, url)
            if html is None:
                print(f"FAILED {key} — no HTML returned")
                continue

            teams = extract_offensive_four_factors(html, year)

            seasons[key] = {
                "season": season_label(year),
                "season_type": "Regular Season",
                "source": "Basketball-Reference Team Advanced/Four Factors",
                "teams": teams,
            }

            save_cache(data)

            print(f"OK {key} — offensive Four Factors teams={len(teams)}")
            print("    Cache checkpoint saved.")

        except ScraperBlocked as exc:
            print(f"SCRAPER STOPPED {key} — {exc}")
            print("No Retry-After wait. No bypass. Existing cache preserved.")
            break

        except Exception as exc:
            print(f"ERROR {key} — {exc}")
            print("    Continuing to next season.")

    completed = len(seasons)
    print()
    print("=" * 88)
    print("SCRAPE RUN COMPLETE")
    print("=" * 88)
    print(f"Completed season maps: {completed}")
    print(f"Cache: {JSON_CACHE}")


if __name__ == "__main__":
    main()
