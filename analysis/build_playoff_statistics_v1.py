r"""
NBA PER-75 — PLAYOFF STATISTICAL LAYER V1

Purpose
-------
Convert the verified canonical playoff player-season identity layer into the
same core Per-100 -> Per-75 framework used by the project's historical
Basketball-Reference pipeline.

Methodology
-----------
1952-1973:
    Basketball-Reference playoff player totals
    + playoff team Pace from the season summary
    -> estimated player possessions
    -> Per-100
    -> Per-75

1974-2026:
    Basketball-Reference playoff Per-100 table
    -> Per-75

This follows the project's established methodology:
1951-52 through 1972-73 uses player totals + team Pace to estimate possessions;
1973-74 onward uses Basketball-Reference Per-100 data. Per-75 is Per-100 * 0.75.

Important
---------
- The identity layer is NOT changed.
- Unresolved identities are NOT guessed.
- Raw B-Ref totals are preserved.
- Missing historical statistics remain missing; they are not converted to zero.
- The canonical input is `nba_per75_playoffs_player_season_v4.csv`.
- This script writes a new playoff statistics layer only.

Requirements
------------
pip install pandas requests beautifulsoup4 lxml

Run
---
python analysis\build_playoff_statistics_v1.py
"""

from __future__ import annotations

from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
import re
import time
import unicodedata

import pandas as pd
import requests

ROOT = Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75")
INPUT = ROOT / "data" / "nba_per75_playoffs_player_season_v4.csv"
RAW = ROOT / "data" / "nba_per75_playoffs_bref_v1.csv"

OUT = ROOT / "data" / "nba_per75_playoffs_stats_v1.csv"
AUDIT = ROOT / "data" / "nba_per75_playoffs_stats_build_audit_v1.csv"

FIRST_YEAR = 1952
LAST_YEAR = 2026
MODERN_START = 1974
PER75_SCALE = 0.75

RATE_COLUMNS = [
    "FG","FGA","3P","3PA","2P","2PA","FT","FTA",
    "ORB","DRB","TRB","AST","STL","BLK","TOV","PF","PTS"
]

REQUEST_DELAY = 1.25
TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class CommentExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.comments = []

    def handle_comment(self, data):
        self.comments.append(data)


def norm_name(v):
    s = "" if pd.isna(v) else str(v)
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode("ascii")
    s = s.casefold()
    s = re.sub(r"[\*\u2020\u2021]+", "", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def flatten(df):
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        cols=[]
        for c in df.columns:
            vals=[str(x).strip() for x in c if str(x).strip() and str(x).strip().lower()!="nan"]
            cols.append(vals[-1] if vals else "")
        df.columns=cols
    return df


def read_tables(html):
    tables=[]
    try:
        tables.extend(pd.read_html(StringIO(html)))
    except Exception:
        pass

    parser=CommentExtractor()
    parser.feed(html)
    for comment in parser.comments:
        if "<table" not in comment.lower():
            continue
        try:
            tables.extend(pd.read_html(StringIO(comment)))
        except Exception:
            continue

    return [flatten(t) for t in tables if isinstance(t,pd.DataFrame)]


def fetch(session, url):
    time.sleep(REQUEST_DELAY)
    r=session.get(url,headers=HEADERS,timeout=TIMEOUT)
    if r.status_code in (403,429):
        raise RuntimeError(f"Basketball-Reference blocked request ({r.status_code}): {url}")
    r.raise_for_status()
    return r.text


def find_table(tables, required, preferred=None):
    preferred=preferred or []
    best=None
    best_score=-1
    for t in tables:
        cols={str(c).strip() for c in t.columns}
        if not set(required).issubset(cols):
            continue
        score=len(set(preferred).intersection(cols))
        if score>best_score:
            best=t
            best_score=score
    return best


def season_label(year):
    return f"{year-1}-{str(year)[-2:]}"


def get_playoff_pace(session, year):
    """Extract playoff team Pace from the B-Ref playoff summary."""
    url=f"https://www.basketball-reference.com/playoffs/NBA_{year}.html"
    html=fetch(session,url)
    tables=read_tables(html)

    for t in tables:
        cols={str(c).strip() for c in t.columns}
        if "Team" not in cols or "Pace" not in cols:
            continue
        result={}
        for _,r in t.iterrows():
            team=str(r.get("Team","")).strip()
            try:
                pace=float(r.get("Pace"))
            except (TypeError,ValueError):
                continue
            if team and 50 <= pace <= 150:
                result[team]=pace
        if result:
            return result
    return {}


def get_playoff_per100(session, year):
    """Extract the Basketball-Reference playoff Per-100 player table."""
    url=f"https://www.basketball-reference.com/playoffs/NBA_{year}_per_poss.html"
    html=fetch(session,url)
    tables=read_tables(html)

    table=find_table(
        tables,
        {"Player","MP"},
        preferred=set(RATE_COLUMNS) | {"PTS","FGA","TRB","AST"}
    )
    if table is None:
        raise ValueError(f"Could not find playoff Per-100 player table for {season_label(year)}.")

    # Keep the first actual player row for each normalized name. B-Ref may expose
    # repeated header rows inside the HTML.
    table=table.copy()
    table=table[table["Player"].astype(str).str.strip().ne("Player")]
    table["_PlayerKey"]=table["Player"].map(norm_name)
    table=table.loc[table["_PlayerKey"].ne("")].copy()

    # Prefer the aggregate row where B-Ref provides one (TOT/2TM/etc.).
    team_col="Team" if "Team" in table.columns else ("Tm" if "Tm" in table.columns else None)
    if team_col:
        def rank_team(v):
            s=str(v).strip().upper()
            if s=="TOT": return 0
            m=re.fullmatch(r"(\d+)TM",s)
            return int(m.group(1)) if m else -1
        table["_rank"]=table[team_col].map(rank_team)
        rows=[]
        for _,g in table.groupby("_PlayerKey",sort=False):
            ag=g[g["_rank"]>=0]
            if not ag.empty:
                rows.append(ag.sort_values("_rank",ascending=False).iloc[0])
            else:
                rows.append(g.iloc[0])
        table=pd.DataFrame(rows)

    rename={}
    for c in RATE_COLUMNS:
        if c in table.columns:
            rename[c]=f"{c}_per100"
    table=table.rename(columns=rename)

    keep=["Player","MP"]+[f"{c}_per100" for c in RATE_COLUMNS if f"{c}_per100" in table.columns]
    if "Team" in table.columns: keep.append("Team")
    if "Tm" in table.columns: keep.append("Tm")
    return table[[c for c in keep if c in table.columns]].copy()


def add_per75_from_per100(df):
    for c in RATE_COLUMNS:
        p=f"{c}_per100"
        q=f"{c}_per75"
        if p in df.columns:
            df[q]=(pd.to_numeric(df[p],errors="coerce")*PER75_SCALE).round(2)
    return df


def historical_possessions(canonical, pace):
    out=canonical.copy()

    # The canonical V4 row may contain multiple teams in `Teams` and a combined MP.
    # For a multi-team row, use the raw B-Ref rows so each stint can use its own pace.
    raw=pd.read_csv(RAW,low_memory=False)

    # Match only resolved canonical identities by player name + season. This is
    # a statistical denominator calculation, not an identity resolver.
    raw["_PlayerKey"]=raw["Player"].map(norm_name)
    raw["_Year"]=pd.to_numeric(raw["Season"],errors="coerce")

    canonical["_PlayerKey"]=canonical["Player"].map(norm_name)
    canonical["_Year"]=pd.to_numeric(canonical["Season"],errors="coerce")

    raw_counts=raw.groupby(["_PlayerKey","_Year"],dropna=False).size()

    possessions=[]
    missing=[]
    for _,r in canonical.iterrows():
        key=(r["_PlayerKey"],r["_Year"])
        g=raw.loc[(raw["_PlayerKey"]==key[0]) & (raw["_Year"]==key[1])].copy()

        if g.empty:
            possessions.append(pd.NA)
            missing.append("")
            continue

        total=0.0
        missing_teams=[]
        valid=False
        for _,stint in g.iterrows():
            mp=pd.to_numeric(stint.get("MP"),errors="coerce")
            if pd.isna(mp) or mp<=0:
                continue
            team=str(stint.get("Team","")).strip()
            p=pace.get(team)
            if p is None:
                p=pace.get(team.upper())
            if p is None:
                # Use season mean only as the same historical fallback used by
                # the project's established pipeline.
                vals=[float(x) for x in pace.values() if pd.notna(x) and float(x)>0]
                p=sum(vals)/len(vals) if vals else None
                if p is not None:
                    missing_teams.append(team)
            if p is not None:
                total += float(p)*float(mp)/48.0
                valid=True

        possessions.append(total if valid and total>0 else pd.NA)
        missing.append(",".join(dict.fromkeys(missing_teams)))

    out["Estimated_Possessions"]=possessions
    out["Missing_Team_Pace"]=missing
    return out


def add_historical_per100(df):
    poss=pd.to_numeric(df["Estimated_Possessions"],errors="coerce")
    valid=poss.notna() & (poss>0)
    for c in RATE_COLUMNS:
        if c not in df.columns:
            continue
        q=f"{c}_per100"
        df[q]=pd.NA
        v=pd.to_numeric(df[c],errors="coerce")
        mask=valid & v.notna()
        df.loc[mask,q]=v[mask]/poss[mask]*100.0
    return df


def add_efficiency(df):
    fga=pd.to_numeric(df.get("FGA"),errors="coerce")
    fta=pd.to_numeric(df.get("FTA"),errors="coerce")
    pts=pd.to_numeric(df.get("PTS"),errors="coerce")
    denom=2*(fga+0.44*fta)
    df["TS_pct"]=pts/denom
    df["TS_pct"]=df["TS_pct"].where(denom>0)
    return df


def main():
    if not INPUT.exists():
        raise FileNotFoundError(f"Missing canonical playoff identity file: {INPUT}")

    canonical=pd.read_csv(INPUT,low_memory=False)
    required={"Player_ID","Player","Season","Season_Type","MP","PTS"}
    missing=required-set(canonical.columns)
    if missing:
        raise ValueError(f"Canonical playoff file missing columns: {sorted(missing)}")

    canonical=canonical.loc[
        canonical["Season_Type"].astype(str).str.casefold().eq("playoffs")
    ].copy()

    canonical["Season"]=pd.to_numeric(canonical["Season"],errors="coerce")
    canonical=canonical.dropna(subset=["Season"])
    canonical["Season"]=canonical["Season"].astype(int)

    session=requests.Session()

    historical_frames=[]
    modern_frames=[]
    audit_rows=[]

    print("="*88)
    print("NBA PER-75 — PLAYOFF STATISTICAL LAYER V1")
    print("="*88)
    print(f"Canonical playoff player-seasons: {len(canonical):,}")
    print("Methodology: 1952-73 estimated possessions -> Per-100 -> Per-75;")
    print("             1974-2026 B-Ref Per-100 -> Per-75")
    print()

    # Historical: B-Ref totals already exist locally, so only the playoff
    # summary Pace page must be retrieved.
    for y in range(FIRST_YEAR,MODERN_START):
        c=canonical.loc[canonical["Season"].eq(y)].copy()
        if c.empty:
            continue
        try:
            pace=get_playoff_pace(session,y)
            h=historical_possessions(c,pace)
            h=add_historical_per100(h)
            h=add_per75_from_per100(h)
            h["Per75_Source"]="Estimated possessions from B-Ref playoff Team Pace"
            historical_frames.append(h)
            audit_rows.append({
                "Season":y,"Method":"Historical totals + playoff Team Pace",
                "Canonical_Rows":len(c),"Pace_Teams":len(pace),
                "Rows_With_Estimated_Possessions":int(pd.to_numeric(h["Estimated_Possessions"],errors="coerce").notna().sum()),
                "Status":"OK"
            })
            print(f"{y}: historical Per-75 built — {len(h):,} player-seasons; {len(pace):,} team pace rows")
        except Exception as exc:
            audit_rows.append({
                "Season":y,"Method":"Historical totals + playoff Team Pace",
                "Canonical_Rows":len(c),"Pace_Teams":0,
                "Rows_With_Estimated_Possessions":0,
                "Status":f"FAILED: {exc}"
            })
            print(f"{y}: FAILED — {exc}")

    # Modern: B-Ref's own Per-100 playoff table is authoritative.
    for y in range(MODERN_START,LAST_YEAR+1):
        c=canonical.loc[canonical["Season"].eq(y)].copy()
        if c.empty:
            continue
        try:
            p100=get_playoff_per100(session,y)
            p100["_PlayerKey"]=p100["Player"].map(norm_name)
            c["_PlayerKey"]=c["Player"].map(norm_name)

            # Merge by canonical player's normalized B-Ref name. Identity is
            # already resolved in V25; this merge only transfers rate statistics.
            merged=c.merge(
                p100.drop_duplicates("_PlayerKey"),
                on="_PlayerKey",how="left",suffixes=("","_BRefPer100")
            )
            merged=add_per75_from_per100(merged)
            merged["Per75_Source"]="Basketball-Reference playoff Per-100"
            modern_frames.append(merged)

            rate_hits=merged["PTS_per100"].notna().sum() if "PTS_per100" in merged else 0
            audit_rows.append({
                "Season":y,"Method":"B-Ref playoff Per-100",
                "Canonical_Rows":len(c),"Per100_Player_Rows":len(p100),
                "Rows_With_Per100_PTS":int(rate_hits),
                "Status":"OK"
            })
            print(f"{y}: modern Per-75 built — {len(merged):,} player-seasons; {int(rate_hits):,} matched Per-100")
        except Exception as exc:
            audit_rows.append({
                "Season":y,"Method":"B-Ref playoff Per-100",
                "Canonical_Rows":len(c),"Per100_Player_Rows":0,
                "Rows_With_Per100_PTS":0,
                "Status":f"FAILED: {exc}"
            })
            print(f"{y}: FAILED — {exc}")

    frames=historical_frames+modern_frames
    if not frames:
        raise RuntimeError("No playoff statistical rows were produced.")

    result=pd.concat(frames,ignore_index=True,sort=False)

    # Remove helper columns and keep a stable schema.
    result=result.drop(columns=["_PlayerKey","_Year"],errors="ignore")
    result["Season"]=pd.to_numeric(result["Season"],errors="coerce").astype("Int64")

    # Recalculate basic shooting/efficiency rates from raw totals so the playoff
    # layer is internally consistent, without inventing missing source stats.
    for pct,num,den in [("FG%","FG","FGA"),("3P%","3P","3PA"),("2P%","2P","2PA"),("FT%","FT","FTA")]:
        if num in result.columns and den in result.columns:
            n=pd.to_numeric(result[num],errors="coerce")
            d=pd.to_numeric(result[den],errors="coerce")
            result[pct]=n/d
            result.loc[d<=0,pct]=pd.NA

    result=add_efficiency(result)

    # Structural checks.
    if result.duplicated(["Player_ID","Season","Season_Type"]).any():
        dup=result[result.duplicated(["Player_ID","Season","Season_Type"],keep=False)]
        raise ValueError(f"Duplicate canonical playoff player-seasons remain: {len(dup):,}")

    expected=set(canonical[["Player_ID","Season"]].itertuples(index=False,name=None))
    actual=set(result[["Player_ID","Season"]].itertuples(index=False,name=None))
    missing_pairs=expected-actual
    if missing_pairs:
        print(f"WARNING: {len(missing_pairs):,} canonical player-seasons have no statistical output.")

    result.to_csv(OUT,index=False)
    pd.DataFrame(audit_rows).to_csv(AUDIT,index=False)

    print()
    print("="*88)
    print("BUILD COMPLETE")
    print("="*88)
    print(f"Canonical input rows:       {len(canonical):,}")
    print(f"Statistical output rows:    {len(result):,}")
    print(f"Players:                    {result['Player_ID'].nunique():,}")
    print(f"Seasons:                    {result['Season'].nunique():,}")
    print(f"Per-75 PTS rows:            {int(result.get('PTS_per75',pd.Series(dtype=float)).notna().sum()):,}")
    print(f"Output:                     {OUT}")
    print(f"Audit:                      {AUDIT}")
    print()
    print("No playoff identity decisions were changed.")
    print("No fuzzy matching or identity guessing was performed.")

if __name__=="__main__":
    main()
