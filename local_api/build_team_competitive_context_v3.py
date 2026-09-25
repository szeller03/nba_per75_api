"""NBA PER-75 — Team Competitive Context Builder V3

Purpose
-------
Build the missing competitive-context layer for the Teams page:
  * Land of Basketball -> regular-season seed/conference/W-L/postseason qualification
  * Basketball-Reference -> playoff round reached / eliminated / champion / Finals

V3 changes
----------
* NEVER loops over 75 Basketball-Reference season pages.
* NEVER retries a 429 indefinitely.
* Prefer a user-supplied local Basketball-Reference `series.html` export.
* If B-Ref is not supplied locally, make at most one polite fetch attempt and
  record the result; the standings build continues independently.
* Land of Basketball parsing no longer depends on a specific table header layout.
  It recognizes rows whose first cell contains a seed such as `1.` and whose next
  cell is a team name, matching the structure shown on the source pages.
* Corrects historical team-key aliases used when matching the two sources.
* Writes resumable raw-source caches and a detailed validation report.

Recommended usage
-----------------
1. Download the Basketball-Reference all-time playoff series page in a normal
   browser and save it as:
       local_api/cache/team_competitive_sources_v3/bref_playoff_series_history.html
   The source is: https://www.basketball-reference.com/playoffs/series.html
2. Run:
       python local_api/build_team_competitive_context_v3.py

You may also provide the saved HTML explicitly:
       python local_api/build_team_competitive_context_v3.py --bref-html "C:\\path\\series.html"

Or skip B-Ref entirely while testing standings:
       python local_api/build_team_competitive_context_v3.py --skip-bref
"""
from __future__ import annotations

import argparse
import json
import random
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[0].parent
MASTER = ROOT / "data" / "nba_per75_team_master_enriched.csv"
OUT = ROOT / "local_api" / "cache" / "team_competitive_context_v3.json"
REPORT = OUT.with_name("team_competitive_context_v3_build_report.json")
RAW = ROOT / "local_api" / "cache" / "team_competitive_sources_v3"
RAW.mkdir(parents=True, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36 NBA-PER-75 historical reference builder/3.0"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

ALIASES = {
    "okc": "oklahomacitythunder", "oklahomacity": "oklahomacitythunder",
    "seattle": "seattlesupersonics", "nj": "brooklynnets", "newjersey": "brooklynnets",
    "la": "losangeleslakers", "gs": "goldenstatewarriors", "gsw": "goldenstatewarriors",
    "ny": "newyorkknicks", "nyk": "newyorkknicks", "phx": "phoenixsuns", "pho": "phoenixsuns",
    "sas": "sanantoniospurs", "sa": "sanantoniospurs", "uta": "utahjazz", "was": "washingtonwizards",
    "wsh": "washingtonwizards", "nop": "neworleanspelicans", "no": "neworleanspelicans",
    "nohl": "neworleanspelicans", "lac": "losangelesclippers", "lal": "losangeleslakers",
    "van": "memphisgrizzlies", "sea": "seattlesupersonics", "njn": "brooklynnets",
    "kck": "sacramentokings", "kco": "sacramentokings", "cin": "sacramentokings",
    "sdc": "losangelesclippers", "sd": "losangelesclippers", "buf": "losangelesclippers",
    "stl": "atlantahawks", "mlh": "atlantahawks", "tri": "atlantahawks", "phw": "goldenstatewarriors",
    "sfw": "goldenstatewarriors", "chp": "washingtonwizards", "chz": "washingtonwizards",
    "blb": "washingtonwizards", "cap": "washingtonwizards", "wsb": "washingtonwizards",
    "ftw": "detroitpistons", "syr": "philadelphia76ers", "roc": "sacramentokings",
    "ino": "indianapacers", "ind": "indianapacers", "phi": "philadelphia76ers", "phl": "philadelphia76ers",
    "bkn": "brooklynnets", "por": "portlandtrailblazers", "den": "denvernuggets",
    "min": "minnesotatimberwolves", "mil": "milwaukeebucks", "chi": "chicagobulls",
    "bos": "bostonceltics", "cle": "clevelandcavaliers", "det": "detroitpistons",
    "atl": "atlantahawks", "hou": "houstonrockets", "mem": "memphisgrizzlies",
    "orl": "orlandomagic", "sac": "sacramentokings", "tor": "torontoraptors",
    "indianapacers": "indianapacers",
}

ROUND_RANK = {
    "DIVISION SEMIFINALS": 1, "DIVISION SEMIFINAL": 1,
    "FIRST ROUND": 1, "CONFERENCE FIRST ROUND": 1, "QUARTERFINALS": 1,
    "DIVISION FINALS": 2, "DIVISION FINAL": 2,
    "CONFERENCE SEMIFINALS": 2, "CONFERENCE SEMIFINAL": 2, "SEMIFINALS": 2,
    "CONFERENCE FINALS": 3, "CONFERENCE FINAL": 3,
    "FINALS": 4,
}


def clean(x):
    return re.sub(r"\s+", " ", str(x or "").replace("\xa0", " ")).strip()


def key(x):
    s = re.sub(r"[^a-z0-9]", "", clean(x).lower())
    return ALIASES.get(s, s)


def end_year(season):
    s = clean(season)
    m = re.search(r"(\d{4})\s*[-/–]\s*(\d{2,4})$", s)
    if m:
        start, tail = int(m.group(1)), m.group(2)
        if len(tail) == 4:
            return int(tail)
        candidate = (start // 100) * 100 + int(tail)
        if candidate <= start:
            candidate += 100
        return candidate
    m = re.search(r"(\d{4})$", s)
    return int(m.group(1)) if m else None


def season_bounds(season):
    y = end_year(season)
    return (y - 1, y) if y else (None, None)


def fetch_once(url, path, delay=1.0):
    if path.exists() and path.stat().st_size > 0:
        return path.read_text(encoding="utf-8", errors="ignore"), {"cached": True, "status": 200}
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 429:
            raise RuntimeError("HTTP 429 Too Many Requests")
        r.raise_for_status()
        text = r.text
        path.write_text(text, encoding="utf-8")
        time.sleep(max(0.0, delay) + random.uniform(0.1, 0.3))
        return text, {"cached": False, "status": r.status_code}
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def rank_from_text(text):
    m = re.match(r"^(\d{1,2})\s*\.?\s*$", clean(text))
    return int(m.group(1)) if m else None


def parse_land_standings(html, season):
    soup = BeautifulSoup(html, "html.parser")
    rows, seen = [], set()

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            vals = [clean(c.get_text(" ")) for c in cells]
            if len(vals) < 4:
                continue

            seed = rank_from_text(vals[0])
            team_cell = vals[1]
            if seed is None:
                # Some HTML layouts put `1.` and the team in the same text node.
                m = re.match(r"^(\d{1,2})\.?\s+(.+)$", team_cell)
                if m:
                    seed, team_cell = int(m.group(1)), clean(m.group(2))
            if seed is None or not (1 <= seed <= 30):
                continue
            if not team_cell or team_cell.lower() in {"team", "teams"}:
                continue

            tk = key(team_cell)
            if tk in seen:
                continue

            # The source's conference table rows have W/L immediately after Team.
            wins = losses = None
            try:
                wins = int(re.sub(r"[^0-9]", "", vals[2]))
                losses = int(re.sub(r"[^0-9]", "", vals[3]))
            except Exception:
                pass

            row_text = " ".join(vals)
            qualification = ""
            if re.search(r"\bpi\b", row_text, re.I):
                qualification = "PLAY-IN"
            elif re.search(r"\bp\b", row_text, re.I):
                qualification = "PLAYOFFS"

            # Identify conference from the nearest heading, but never require it.
            conference = None
            node = table
            for _ in range(12):
                node = node.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
                if not node:
                    break
                ht = clean(node.get_text(" "))
                if re.search(r"Western Conference", ht, re.I):
                    conference = "Western"
                    break
                if re.search(r"Eastern Conference", ht, re.I):
                    conference = "Eastern"
                    break

            rows.append({
                "season": season, "team": team_cell, "team_key": tk, "seed": seed,
                "conference": conference, "wins": wins, "losses": losses,
                "postseason_qualification": qualification,
                "source": "Land of Basketball",
            })
            seen.add(tk)
    return rows


def normalize_round(raw):
    s = clean(raw).lower()
    s = re.sub(r"\b(eastern|western)\s+", "", s)
    s = re.sub(r"\bconf\b", "conference", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s in {"final", "finals"}: return "FINALS"
    if "conference finals" in s: return "CONFERENCE FINALS"
    if "conference semifinals" in s: return "CONFERENCE SEMIFINALS"
    if "conference first round" in s or "first round" in s: return "FIRST ROUND"
    if "division finals" in s: return "DIVISION FINALS"
    if "division semifinals" in s: return "DIVISION SEMIFINALS"
    if "semifinal" in s: return "SEMIFINALS"
    if "quarterfinal" in s: return "QUARTERFINALS"
    return clean(raw).upper()


def parse_bref_series_history(html):
    # Use pandas to read the source's actual table, then robustly identify columns.
    tables = pd.read_html(html)
    series = []
    for t in tables:
        if isinstance(t.columns, pd.MultiIndex):
            t.columns = [" | ".join(str(x) for x in c if str(x).lower() != "nan").strip() for c in t.columns]
        else:
            t.columns = [str(c) for c in t.columns]
        cols = [clean(c).lower() for c in t.columns]

        def find_col(*names):
            for n in names:
                for i, c in enumerate(cols):
                    if c == n or c.endswith("| " + n):
                        return i
            for n in names:
                for i, c in enumerate(cols):
                    if n in c:
                        return i
            return None

        yi = find_col("yr", "year")
        li = find_col("lg", "league")
        ri = find_col("series", "round")
        wi = find_col("team", "winner")
        # In this table there are two `Team` columns. Locate the pair after Series.
        if None in (yi, li, ri, wi):
            continue

        # Prefer columns whose raw names correspond to Team and identify the first/second occurrence.
        team_cols = [i for i, c in enumerate(cols) if c in {"team", "team | team"} or c.endswith("| team")]
        if len(team_cols) < 2:
            # Common pandas representation: the two team columns are adjacent after Series.
            team_cols = [i for i, c in enumerate(cols) if c == "team"]
        if len(team_cols) < 2:
            continue
        wteam_i, lteam_i = team_cols[0], team_cols[1]

        for _, row in t.iterrows():
            lg = clean(row.iloc[li]).upper()
            if lg and lg != "NBA":
                continue
            m = re.search(r"(\d{4})", clean(row.iloc[yi]))
            if not m:
                continue
            winner = clean(row.iloc[wteam_i])
            loser = clean(row.iloc[lteam_i])
            rd = normalize_round(row.iloc[ri])
            if not winner or not loser or winner.lower() == "nan" or loser.lower() == "nan":
                continue
            series.append({
                "year": int(m.group(1)), "league": "NBA", "round": rd,
                "winner": re.sub(r"\s*\(\d+\)\s*$", "", winner),
                "loser": re.sub(r"\s*\(\d+\)\s*$", "", loser),
            })
    # De-duplicate exact rows while preserving order.
    out, seen = [], set()
    for s in series:
        sig = (s["year"], s["round"], s["winner"], s["loser"])
        if sig not in seen:
            out.append(s); seen.add(sig)
    return out


def playoff_outcomes(series, season_year):
    by = {}
    season_series = [s for s in series if s["year"] == season_year and s.get("league", "NBA") == "NBA"]
    for s in season_series:
        rd = s["round"]
        rr = ROUND_RANK.get(rd, 0)
        for tm, won in ((s["winner"], True), (s["loser"], False)):
            k = key(tm)
            if not k:
                continue
            cur = by.get(k)
            if cur is None or rr > cur["round_rank"]:
                by[k] = {
                    "season_end_year": season_year, "team": tm, "team_key": k,
                    "playoff_round": rd, "round_rank": rr,
                    "source": "Basketball-Reference",
                }
    for s in season_series:
        if s["round"] == "FINALS":
            wk, lk = key(s["winner"]), key(s["loser"])
            if wk in by:
                by[wk].update(playoff_finish="CHAMPION", playoff_status="CHAMPION")
            if lk in by:
                by[lk].update(playoff_finish="MADE FINALS", playoff_status="MADE FINALS")
    for o in by.values():
        if "playoff_finish" not in o:
            o["playoff_finish"] = o["playoff_round"]
            o["playoff_status"] = o["playoff_round"]
        o.pop("round_rank", None)
    return by


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--bref-html", default=None, help="Path to a locally saved Basketball-Reference playoffs/series.html")
    ap.add_argument("--skip-bref", action="store_true")
    ap.add_argument("--no-land-cache", action="store_true")
    args = ap.parse_args()

    df = pd.read_csv(MASTER, low_memory=False)
    seasons = sorted({str(x) for x in df["Season"].dropna()}, key=lambda s: end_year(s) or 0)
    seasons = [s for s in seasons if end_year(s) and (args.start is None or end_year(s) >= args.start) and (args.end is None or end_year(s) <= args.end)]

    failures = []
    result = {
        "version": 3,
        "sources": {
            "standings": "https://www.landofbasketball.com/yearbyyear/YYYY_YYYY_standings.htm",
            "playoffs": "https://www.basketball-reference.com/playoffs/series.html",
        },
        "seasons": {},
    }

    series = []
    bref_source = None
    if not args.skip_bref:
        candidate = Path(args.bref_html) if args.bref_html else RAW / "bref_playoff_series_history.html"
        print("[Basketball-Reference] playoff series history")
        if candidate.exists() and candidate.stat().st_size > 0:
            try:
                series = parse_bref_series_history(candidate.read_text(encoding="utf-8", errors="ignore"))
                bref_source = str(candidate)
                print(f"  local source: {candidate}")
                print(f"  series parsed: {len(series)}")
            except Exception as exc:
                failures.append(("ALL", "playoffs", f"local parse failed: {exc}"))
                print(f"  local parse failed: {exc}")
        else:
            # One attempt only. A 429 is recorded and never retried.
            try:
                text, _ = fetch_once("https://www.basketball-reference.com/playoffs/series.html", candidate, args.delay)
                series = parse_bref_series_history(text)
                bref_source = str(candidate)
                print(f"  series parsed: {len(series)}")
            except Exception as exc:
                failures.append(("ALL", "playoffs", str(exc)))
                print(f"  source not fetched: {exc}")
                print("  TIP: save the B-Ref series page in a normal browser and rerun with --bref-html <file>")
    else:
        print("[Basketball-Reference] skipped (--skip-bref)")

    land_success = 0
    land_rows = 0
    finish_rows = 0
    for season in seasons:
        sy, ey = season_bounds(season)
        print(f"[{season}] standings")
        sfile = RAW / f"land_{ey}.html"
        try:
            if args.no_land_cache and sfile.exists():
                sfile.unlink()
            html, _ = fetch_once(f"https://www.landofbasketball.com/yearbyyear/{sy}_{ey}_standings.htm", sfile, args.delay)
            standings = parse_land_standings(html, season)
            if standings:
                land_success += 1
            land_rows += len(standings)
        except Exception as exc:
            print("  standings failed:", exc)
            standings = []
            failures.append((season, "standings", str(exc)))
        print(f"  seeds parsed: {len(standings)}")

        outcomes = playoff_outcomes(series, ey)
        finish_rows += len(outcomes)
        print(f"[{season}] playoffs")
        print(f"  playoff teams parsed: {len(outcomes)}, series: {sum(1 for s in series if s['year'] == ey)}")

        by = {r["team_key"]: dict(r) for r in standings}
        for k, r in outcomes.items():
            by.setdefault(k, {}).update(r)
        for r in by.values():
            if "playoff_finish" not in r:
                q = r.get("postseason_qualification")
                if q == "PLAY-IN" or r.get("seed") in (9, 10):
                    r["playoff_finish"] = "PLAY-IN / MISSED PLAYOFFS"
                    r["playoff_status"] = "PLAY-IN / MISSED PLAYOFFS"
                else:
                    r["playoff_finish"] = "MISSED PLAYOFFS"
                    r["playoff_status"] = "MISSED PLAYOFFS"
        result["seasons"][season] = list(by.values())

    result["metadata"] = {
        "seasons_requested": len(seasons),
        "standings_seasons_with_rows": land_success,
        "standings_rows": land_rows,
        "playoff_finish_rows": finish_rows,
        "bref_source": bref_source,
        "failures": failures,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT.write_text(json.dumps(result["metadata"], indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nBUILD COMPLETE")
    print(f"SEASONS {len(seasons)}")
    print(f"STANDINGS SEASONS {land_success}")
    print(f"SEED ROWS {land_rows}")
    print(f"PLAYOFF FINISH ROWS {finish_rows}")
    print(f"FAILURES {len(failures)}")
    if failures:
        print("FAILURE DETAILS:")
        for f in failures[:20]:
            print(" ", f)
    print(f"WROTE {OUT}")
    print(f"WROTE {REPORT}")


if __name__ == "__main__":
    main()
