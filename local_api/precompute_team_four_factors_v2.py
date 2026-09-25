from __future__ import annotations

import argparse
import io
import json
import random
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup, Comment

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
CACHE_DIR = HERE.parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE = CACHE_DIR / "bref_team_four_factors_v2.json"

FIRST_YEAR = 1952
LAST_YEAR = 2026

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


class BRefRateLimited(RuntimeError):
    pass


def season_key(year: int, season_type: str) -> str:
    return f"{season_type}|{year - 1}-{str(year)[-2:]}"


def bref_key(value: object) -> str:
    return re.sub(
        r"\s+", " ",
        re.sub(r"[^a-z0-9]+", " ", str(value).replace("*", "").lower()).strip(),
    )


def flat_col(value) -> str:
    if isinstance(value, tuple):
        return " | ".join(
            str(x).strip()
            for x in value
            if str(x).strip() and str(x).lower() != "nan"
        )
    return str(value).strip()


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [flat_col(c) for c in df.columns]
    else:
        df.columns = [str(c).strip() for c in df.columns]
    return df


def all_tables(html: str) -> list[pd.DataFrame]:
    """Read both normal and B-Ref comment-wrapped tables."""
    chunks = [html]
    soup = BeautifulSoup(html, "html.parser")
    chunks.extend(
        str(comment)
        for comment in soup.find_all(string=lambda x: isinstance(x, Comment))
        if "<table" in str(comment).lower()
    )

    tables: list[pd.DataFrame] = []
    for chunk in chunks:
        try:
            tables.extend(pd.read_html(io.StringIO(chunk)))
        except (ValueError, ImportError):
            pass
    return tables


def _factor_indices(columns: list[str], name: str) -> list[int]:
    target = name.lower()
    out = []
    for i, col in enumerate(columns):
        low = col.lower().strip()
        if low == target or low.endswith("| " + target):
            out.append(i)
    return out


def _team_index(columns: list[str]) -> int | None:
    for i, col in enumerate(columns):
        low = col.lower().strip()
        if low in {"team", "tm"} or low.endswith("| team") or low.endswith("| tm"):
            return i
    return None


def _valid_rate(value, low: float, high: float) -> bool:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return False
    return low <= x <= high


def _header_parts(value) -> tuple[str, str]:
    if isinstance(value, tuple):
        parts = [str(x).strip() for x in value if str(x).strip() and str(x).lower() != "nan"]
        if len(parts) >= 2:
            return parts[0], parts[-1]
        if parts:
            return "", parts[0]
        return "", ""
    text = str(value).strip()
    if " | " in text:
        a, b = [x.strip() for x in text.split(" | ", 1)]
        return a, b
    return "", text


def _pick_factor_columns(raw: pd.DataFrame, factor: str) -> list[int]:
    """Return factor column indices in the table's original column order."""
    target = factor.lower()
    out = []
    for i, col in enumerate(list(raw.columns)):
        group, leaf = _header_parts(col)
        if leaf.lower() == target or group.lower() == target:
            out.append(i)
    return out


def _pick_team_column(raw: pd.DataFrame) -> int | None:
    for i, col in enumerate(list(raw.columns)):
        group, leaf = _header_parts(col)
        if leaf.lower() in {"team", "tm"} or group.lower() in {"team", "tm"}:
            return i
    return None


def _to_fraction(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not pd.notna(x):
        return None
    # B-Ref tables normally parse .509 as 0.509. Guard against any
    # presentation that arrives as 50.9 instead.
    if 1.0 < x <= 100.0:
        x /= 100.0
    return x


def _factor_is_valid(name: str, value) -> bool:
    x = _to_fraction(value)
    if x is None:
        return False
    bounds = {
        "efg%": (0.20, 0.75),
        "tov%": (0.05, 0.35),
        "ftr": (0.02, 0.70),
        "ft/fga": (0.02, 0.70),
        "orb%": (0.05, 0.45),
    }
    lo, hi = bounds.get(name.lower(), (0.0, 1.0))
    return lo <= x <= hi


def parse_four_factors(html: str) -> dict[str, dict[str, float | None]] | None:
    """Scrape B-Ref's season-summary Team Advanced Stats table directly.

    IMPORTANT: this function does not read either local team CSV. It keeps
    the original table hierarchy so the first eFG%/TOV%/ORB% columns are the
    offensive Four Factors and the final copies are the defensive/opponent
    Four Factors. FTr is the standalone offensive field in B-Ref's Advanced
    table (it is not duplicated as a second FTr column).
    """
    for raw in all_tables(html):
        if raw.empty:
            continue

        team_idx = _pick_team_column(raw)
        if team_idx is None:
            continue

        normalized = normalize_columns(raw)
        cols = list(normalized.columns)
        required_flat = {"ORtg", "DRtg"}
        if not required_flat.issubset(set(cols)):
            # Header labels may be flattened differently; still allow the
            # table if it clearly contains the Four Factors hierarchy.
            efg_idx = _pick_factor_columns(raw, "eFG%")
            tov_idx = _pick_factor_columns(raw, "TOV%")
            if len(efg_idx) < 2 or len(tov_idx) < 2:
                continue

        efg = _pick_factor_columns(raw, "eFG%")
        tov = _pick_factor_columns(raw, "TOV%")
        orb = _pick_factor_columns(raw, "ORB%")
        ftr = _pick_factor_columns(raw, "FTr")
        if not ftr:
            ftr = _pick_factor_columns(raw, "FT/FGA")

        # Need the duplicated offensive/defensive eFG/TOV columns plus the
        # standalone offensive FTr. ORB% is optional on some old layouts.
        if len(efg) < 2 or len(tov) < 2 or not ftr:
            continue

        rows: dict[str, dict[str, float | None]] = {}
        for _, row in raw.iterrows():
            team = str(row.iloc[team_idx]).strip().replace("*", "")
            if not team or team.lower() in {"nan", "league average", "league", "average"}:
                continue

            efg_off = _to_fraction(row.iloc[efg[0]])
            tov_off = _to_fraction(row.iloc[tov[0]])
            ftr_off = _to_fraction(row.iloc[ftr[0]])
            efg_def = _to_fraction(row.iloc[efg[-1]])
            tov_def = _to_fraction(row.iloc[tov[-1]])
            orb_off = _to_fraction(row.iloc[orb[0]]) if orb else None
            orb_def = _to_fraction(row.iloc[orb[-1]]) if len(orb) >= 2 else None

            if not _factor_is_valid("eFG%", efg_off):
                continue
            if not _factor_is_valid("TOV%", tov_off):
                continue
            if not _factor_is_valid("FTr", ftr_off):
                continue
            if orb_off is not None and not _factor_is_valid("ORB%", orb_off):
                orb_off = None
            if orb_def is not None and not _factor_is_valid("ORB%", orb_def):
                orb_def = None

            rows[bref_key(team)] = {
                "efgpct": efg_off,
                "tovpct": tov_off,
                "ftr": ftr_off,
                "orb_pct": orb_off,
                "opp_efgpct": efg_def,
                "opp_tovpct": tov_def,
                "opp_orb_pct": orb_def,
            }

        if len(rows) >= 5:
            return rows
    return None

def save_cache(cache: dict) -> None:
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(cache, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )
    tmp.replace(CACHE)


def load_cache() -> dict:
    try:
        raw = json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        raw = {}

    seasons = raw.get("seasons") if isinstance(raw.get("seasons"), dict) else {}
    seasons = {k: v for k, v in seasons.items() if isinstance(v, dict) and v}
    completed = set(raw.get("completed", [])) if isinstance(raw.get("completed"), list) else set()

    # Preserve every existing valid map. A season is complete only if its rows
    # contain offensive eFG%, TOV%, and FTr.
    def has_offensive_ff(rows: dict) -> bool:
        return any(
            isinstance(r, dict)
            and r.get("efgpct") is not None
            and r.get("tovpct") is not None
            and r.get("ftr") is not None
            for r in rows.values()
        )

    completed = {
        key for key in completed
        if isinstance(seasons.get(key), dict) and has_offensive_ff(seasons[key])
    }

    return {
        "version": 7,
        "seasons": seasons,
        "completed": sorted(completed),
    }


SCRIPT_VERSION = "v118-direct-persistent"



def _retry_after_seconds(response: requests.Response) -> float:
    value = response.headers.get("Retry-After")
    if not value:
        return 60.0
    try:
        return max(5.0, float(value))
    except ValueError:
        # HTTP-date Retry-After is uncommon here. Fall back to a safe
        # one-minute pause rather than treating the rate limit as fatal.
        return 60.0


def fetch(
    session: requests.Session,
    url: str,
    min_delay: float,
    max_delay: float,
    max_429_retries: int = 0,
) -> str:
    """Fetch one B-Ref page using the proven single-session architecture.

    A 429 is NOT a terminal scraper condition. By default this function
    waits for the server-provided Retry-After interval and retries the SAME
    URL indefinitely. This preserves the historical sweep instead of
    abandoning the current season.

    max_429_retries=0 means unlimited 429 retries. No rate-limit bypass is
    attempted; the scraper simply honors B-Ref's requested cooldown.
    """
    rate_retries = 0
    transient_retries = 0

    while True:
        print(f"    Requesting: {url}")
        try:
            response = session.get(url, headers=HEADERS, timeout=30)
        except requests.RequestException as exc:
            transient_retries += 1
            if transient_retries <= 3:
                delay = min(60.0 * transient_retries, 180.0)
                print(f"    Network error: {exc}; retrying in {delay:.0f}s ({transient_retries}/3)")
                time.sleep(delay)
                continue
            raise

        if response.status_code == 429:
            rate_retries += 1
            retry_after = _retry_after_seconds(response)
            retry_text = response.headers.get("Retry-After", "not supplied")
            print(
                f"    B-Ref HTTP 429 on {url} (Retry-After={retry_text})."
            )
            if max_429_retries and rate_retries > max_429_retries:
                raise BRefRateLimited(
                    f"HTTP 429 after {rate_retries - 1} retries; Retry-After={retry_text}"
                )
            print(
                f"    Rate limit is NOT terminal. Waiting {retry_after:.0f}s "
                f"then retrying the SAME URL (retry #{rate_retries})."
            )
            time.sleep(retry_after)
            continue

        if response.status_code == 403:
            # 403 is treated as a hard block. We do not attempt to bypass it.
            raise BRefRateLimited("HTTP 403 from Basketball-Reference")

        if response.status_code == 404:
            raise RuntimeError(f"B-Ref returned HTTP 404 for {url}")

        if 500 <= response.status_code < 600:
            transient_retries += 1
            if transient_retries <= 5:
                delay = min(30.0 * transient_retries, 180.0)
                print(f"    B-Ref HTTP {response.status_code}; retrying in {delay:.0f}s ({transient_retries}/5)")
                time.sleep(delay)
                continue

        response.raise_for_status()
        html = response.content.decode("utf-8", errors="replace")
        if len(html) < 1000:
            raise RuntimeError(f"Response too short ({len(html)} chars)")

        if max_delay > 0:
            delay = random.uniform(min_delay, max_delay)
            print(f"    Successful request. Waiting {delay:.1f}s before next B-Ref request.")
            time.sleep(delay)
        return html


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build the resumable Basketball-Reference team Four Factors cache using the proven season-summary parser."
    )
    ap.add_argument("--year", type=int, help="Fetch only one B-Ref season-ending year, e.g. 2026 for 2025-26.")
    ap.add_argument("--season-type", choices=["Regular Season", "Playoffs"])
    ap.add_argument("--max-new", type=int, default=0)
    ap.add_argument("--min-delay", type=float, default=10.0)
    ap.add_argument("--max-delay", type=float, default=15.0)
    ap.add_argument("--max-429-retries", type=int, default=0, help="Maximum 429 retries; 0 = unlimited (default).")
    args = ap.parse_args()

    cache = load_cache()
    existing_maps = len(cache["seasons"])
    existing_completed = len(cache["completed"])
    print(f"Loaded existing cache: completed={existing_completed} season_maps={existing_maps}")
    print(f"Four Factors scraper version: {SCRIPT_VERSION}")


    years = [args.year] if args.year else list(range(FIRST_YEAR, LAST_YEAR + 1))
    types = [args.season_type] if args.season_type else ["Regular Season", "Playoffs"]

    jobs = []
    for year in years:
        for season_type in types:
            key = season_key(year, season_type)
            if key in cache["completed"]:
                continue
            url = (
                f"https://www.basketball-reference.com/leagues/NBA_{year}.html"
                if season_type == "Regular Season"
                else f"https://www.basketball-reference.com/playoffs/NBA_{year}.html"
            )
            jobs.append((year, season_type, key, url))

    save_cache(cache)
    print(f"Missing network season maps: {len(jobs)}")
    print("Direct B-Ref only: no local CSV or local HTML source is used for offensive Four Factors.")
    if not jobs:
        print(f"Nothing to fetch. Cache preserved: completed={len(cache['completed'])} season_maps={len(cache['seasons'])}")
        return

    session = requests.Session()
    print("Sequential BRef mode: workers=1")
    print(f"Delay between successful requests: {args.min_delay:g}-{args.max_delay:g}s")
    print("Source: B-Ref season summary Team Advanced/Four Factors table")

    fetched = 0
    pending: list[tuple[str, str]] = []

    for year, season_type, key, url in jobs:
        print(f"Fetching {key}")
        try:
            html = fetch(session, url, args.min_delay, args.max_delay, args.max_429_retries)
            rows = parse_four_factors(html)
            if not rows:
                raise RuntimeError("BRef page fetched successfully but no valid team Four Factors rows were parsed")

            cache["seasons"][key] = rows
            cache["completed"] = sorted(set(cache["completed"]) | {key})
            fetched += 1
            save_cache(cache)
            print(f"OK {key} teams={len(rows)} progress={fetched}/{len(jobs)}")

            if args.max_new and fetched >= args.max_new:
                break

        except BRefRateLimited as exc:
            pending.append((key, repr(exc)))
            print(f"PENDING {key} {exc!r}")
            print("B-Ref returned a hard block (403) or the optional 429 retry limit was reached. Completed maps are preserved.")
            break
        except Exception as exc:
            pending.append((key, repr(exc)))
            print(f"PENDING {key} {exc!r}")
            # Ordinary failures do not corrupt the cache; continue to the next
            # genuinely missing season.

    if pending:
        cache["pending"] = sorted({k for k, _ in pending})
        cache["last_pending_errors"] = {k: e for k, e in pending}
    else:
        cache.pop("pending", None)
        cache.pop("last_pending_errors", None)
    save_cache(cache)

    print(f"Sweep complete. Successful new maps={fetched} pending={len(pending)}")
    print(f"Wrote {CACHE} completed={len(cache['completed'])} season_maps={len(cache['seasons'])}")


if __name__ == "__main__":
    main()
