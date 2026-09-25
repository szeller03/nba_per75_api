from __future__ import annotations
import io, json, re, shutil, time
from pathlib import Path
from urllib.request import Request, urlopen
import pandas as pd

ROOT = Path(__file__).resolve().parent
MASTER = ROOT / "data" / "nba_per75_team_master_enriched.csv"
LEGACY_MASTER = ROOT / "team_data" / "nba_per75_team_master.csv"
LOGO_DIR = ROOT / "team-logos"
CACHE = ROOT / "local_api" / "cache" / "team_analytics_v14.json"

BREF_UA = "Mozilla/5.0 NBA PER-75 historical data build"
FOUR_FACTORS_RAW = "https://raw.githubusercontent.com/Brescou/NBA-dataset-stats-player-team/main/team/team_stats_four_factors_rs.csv"
FRANCHISES_RAW = "https://raw.githubusercontent.com/TGOlson/nba-logos/main/data/franchises.json"
LOGO_RAW_BASE = "https://raw.githubusercontent.com/TGOlson/nba-logos/main/data/img/team/"


def norm(x):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(x).replace("*", "")).strip().lower())


def yr(x):
    m = re.search(r"(\d{4})$", str(x))
    return int(m.group(1)) if m else None


def fetch_bytes(url, timeout=60):
    req = Request(url, headers={"User-Agent": BREF_UA})
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_text(url, timeout=60):
    return fetch_bytes(url, timeout).decode("utf-8", "ignore")


def flatten(cols):
    out = []
    for c in cols:
        if isinstance(c, tuple):
            out.append(" | ".join(str(v).strip() for v in c if str(v).strip() and str(v).lower() != "nan"))
        else:
            out.append(str(c).strip())
    return out


def bref_defense_four_factors(year):
    url = f"https://www.basketball-reference.com/leagues/NBA_{year}.html"
    html = fetch_text(url)
    tables = []
    try:
        tables += pd.read_html(io.StringIO(html))
    except Exception:
        pass
    for comment in re.findall(r"<!--(.*?)-->", html, re.S):
        if "Defense Four Factors" in comment:
            try:
                tables += pd.read_html(io.StringIO(comment))
            except Exception:
                pass
    for t in tables:
        cols = flatten(t.columns)
        low = [c.lower() for c in cols]
        team = next((i for i, c in enumerate(low) if c in ("team", "tm") or c.endswith("| team") or c.endswith("| tm")), None)
        efg = [i for i, c in enumerate(low) if re.search(r"(^|\|)\s*e?fg%\s*(\.1|_2)?$", c)]
        tov = [i for i, c in enumerate(low) if re.search(r"(^|\|)\s*tov%\s*(\.1|_2)?$", c)]
        if team is None or len(efg) < 2 or len(tov) < 2:
            continue
        z = pd.DataFrame({
            "Team": t.iloc[:, team].astype(str),
            "Opponent_eFG%": pd.to_numeric(t.iloc[:, efg[-1]], errors="coerce"),
            "Opponent_TOV%": pd.to_numeric(t.iloc[:, tov[-1]], errors="coerce"),
        })
        return {norm(r.Team): (r["Opponent_eFG%"], r["Opponent_TOV%"]) for _, r in z.iterrows()}
    return {}


def bootstrap_modern():
    raw = pd.read_csv(FOUR_FACTORS_RAW)
    raw["year"] = raw["SEASON"].map(yr)
    return {
        (norm(r.TEAM_NAME), int(r.year)): (r.OPP_EFG_PCT, r.OPP_TOV_PCT)
        for _, r in raw.dropna(subset=["year"]).iterrows()
    }


def save_masters(df):
    MASTER.parent.mkdir(parents=True, exist_ok=True)
    LEGACY_MASTER.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(MASTER, index=False)
    df.to_csv(LEGACY_MASTER, index=False)


def update_stats():
    if not MASTER.exists():
        raise FileNotFoundError(f"Missing canonical Team master: {MASTER}")
    df = pd.read_csv(MASTER, low_memory=False)
    for c in ["Opponent_eFG%", "Opponent_TOV%", "Logo_ID", "Logo_File", "Logo_Source", "Logo_Source_URL"]:
        if c not in df:
            df[c] = pd.NA

    modern = bootstrap_modern()
    modern_hits = 0
    for i, r in df.iterrows():
        y = yr(r["Season"])
        if y is None:
            continue
        k = (norm(r["Team"]), y)
        if k in modern:
            e, t = modern[k]
            if pd.isna(df.at[i, "Opponent_eFG%"]) and pd.notna(e):
                df.at[i, "Opponent_eFG%"] = float(e)
                modern_hits += 1
            if pd.isna(df.at[i, "Opponent_TOV%"]) and pd.notna(t):
                df.at[i, "Opponent_TOV%"] = float(t)
    save_masters(df)
    print(f"Bootstrap opponent-factor rows populated: {modern_hits}")

    # Fill seasons not covered by the bootstrap with Basketball-Reference.
    years = sorted({yr(x) for x in df["Season"].dropna() if yr(x)})
    for y in years:
        mask = df["Season"].map(yr).eq(y) & (df["Opponent_eFG%"].isna() | df["Opponent_TOV%"].isna())
        if not mask.any():
            continue
        print(f"BRef: {y}")
        try:
            lookup = bref_defense_four_factors(y)
        except Exception as exc:
            print(f"  WARNING: could not fetch {y}: {exc}")
            continue
        for i, r in df.loc[mask].iterrows():
            v = lookup.get(norm(r["Team"]))
            if not v:
                continue
            e, t = v
            if pd.isna(df.at[i, "Opponent_eFG%"]) and pd.notna(e):
                df.at[i, "Opponent_eFG%"] = float(e)
            if pd.isna(df.at[i, "Opponent_TOV%"]) and pd.notna(t):
                df.at[i, "Opponent_TOV%"] = float(t)
        save_masters(df)
        time.sleep(0.2)
    return df


def install_logo_assets():
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(MASTER, low_memory=False)
    for c in ["Logo_ID", "Logo_File", "Logo_Source", "Logo_Source_URL"]:
        if c not in df:
            df[c] = pd.NA

    franchises = json.loads(fetch_text(FRANCHISES_RAW))
    mapping = {}
    for fr in franchises:
        for team in fr.get("teams", []):
            if team.get("league") == "NBA":
                mapping[(norm(team.get("name")), int(team["year"]))] = team["id"]

    unique_ids = set()
    for i, r in df.iterrows():
        y = yr(r["Season"])
        fid = mapping.get((norm(r["Team"]), y))
        if not fid:
            continue
        df.at[i, "Logo_ID"] = fid
        df.at[i, "Logo_Source"] = "TGOlson/nba-logos"
        df.at[i, "Logo_Source_URL"] = "https://github.com/TGOlson/nba-logos"
        dest = LOGO_DIR / f"{fid}.png"
        df.at[i, "Logo_File"] = str(Path("team-logos") / dest.name)
        unique_ids.add(fid)

    downloaded = 0
    for fid in sorted(unique_ids):
        dest = LOGO_DIR / f"{fid}.png"
        if dest.exists() and dest.stat().st_size > 0:
            continue
        try:
            dest.write_bytes(fetch_bytes(f"{LOGO_RAW_BASE}{fid}.png"))
            downloaded += 1
        except Exception as exc:
            print(f"  Logo warning {fid}: {exc}")
            # Keep Logo_ID/Logo_File metadata even if the local binary cannot be downloaded.
    save_masters(df)
    print(f"Logo IDs populated: {df['Logo_ID'].notna().sum()} / {len(df)}")
    print(f"Unique local logo files downloaded this run: {downloaded}")
    return df


def invalidate_team_cache():
    # Remove any stale pre-enrichment team cache. The API is also bumped to v14.
    cache_dir = ROOT / "local_api" / "cache"
    if cache_dir.exists():
        for p in cache_dir.glob("team_analytics*.json"):
            try:
                p.unlink()
                print("Removed stale Team cache:", p)
            except Exception as exc:
                print("Cache warning:", exc)


if __name__ == "__main__":
    df = update_stats()
    df = install_logo_assets()
    invalidate_team_cache()
    print("Opponent eFG populated:", df["Opponent_eFG%"].notna().sum(), "/", len(df))
    print("Opponent TOV populated:", df["Opponent_TOV%"].notna().sum(), "/", len(df))
    print("Logo IDs populated:", df["Logo_ID"].notna().sum(), "/", len(df))
    print("Logo files referenced:", df["Logo_File"].notna().sum(), "/", len(df))
    print("Canonical master:", MASTER)
    print("Team-data mirror:", LEGACY_MASTER)
    print("Logo directory:", LOGO_DIR)
