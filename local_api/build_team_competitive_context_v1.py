"""
NBA PER-75 — TEAM COMPETITIVE CONTEXT BUILDER V1

Authoritative source layer for the Teams page:
  Regular-season seed / conference / postseason qualification:
    Land of Basketball year-by-year standings pages
    https://www.landofbasketball.com/yearbyyear/YYYY_YYYY_standings.htm

  Playoff finish / round eliminated:
    Basketball-Reference playoff summary pages
    https://www.basketball-reference.com/playoffs/NBA_YYYY.html

The builder covers every season present in the canonical team master. It writes
one normalized JSON cache that the local API merges into team analytics rows.
It intentionally does not infer seed from the PER-75 analytics Rk column.

Run from the project root:
  python local_api/build_team_competitive_context_v1.py

The build environment needs internet access. Both sources may rate-limit
requests, so the builder caches every successfully fetched season page.
"""
from __future__ import annotations

import argparse, io, json, re, time
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[0].parent
MASTER = ROOT / "data" / "nba_per75_team_master_enriched.csv"
OUT = ROOT / "local_api" / "cache" / "team_competitive_context_v1.json"
RAW = ROOT / "local_api" / "cache" / "team_competitive_sources_v1"
RAW.mkdir(parents=True, exist_ok=True)

UA = "Mozilla/5.0 (compatible; NBA-PER-75 historical reference builder/1.0)"
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}


def clean(x):
    s = re.sub(r"\s+", " ", str(x or "").replace("\xa0", " ")).strip()
    return re.sub(r"\*$", "", s).strip()


def key(x):
    s = re.sub(r"[^a-z0-9]", "", clean(x).lower())
    aliases = {
        "okc": "oklahomacitythunder", "seattle": "seattlesupersonics",
        "nj": "brooklynnets", "newjersey": "brooklynnets",
        "la": "losangeleslakers", "gs": "goldenstatewarriors", "gsw": "goldenstatewarriors",
        "ny": "newyorkknicks", "nyk": "newyorkknicks", "phx": "phoenixsuns", "pho": "phoenixsuns",
        "sas": "sanantoniospurs", "sa": "sanantoniospurs", "uta": "utahjazz",
        "was": "washingtonwizards", "wsh": "washingtonwizards",
        "nop": "neworleanspelicans", "no": "neworleanspelicans", "nohl": "neworleanspelicans",
        "njn": "brooklynnets", "van": "memphisgrizzlies", "sea": "seattlesupersonics",
        "kck": "sacramentokings", "kco": "sacramentokings", "cin": "sacramentokings",
        "sdc": "losangelesclippers", "sd": "losangelesclippers", "buf": "losangelesclippers",
        "stl": "atlantahawks", "mlh": "atlantahawks", "tri": "atlantahawks",
        "phw": "goldenstatewarriors", "sfw": "goldenstatewarriors",
        "chp": "washingtonwizards", "chz": "washingtonwizards",
        "blb": "washingtonwizards", "cap": "washingtonwizards", "wsb": "washingtonwizards",
        "ftw": "detroitpistons", "syr": "philadelphia76ers", "roc": "sacramentokings",
        "ino": "indianapolispacers", "wat": "atlanta hawks",
    }
    return aliases.get(s, s)


def end_year(season):
    """Return the four-digit ending year from season labels like 1951-52 or 2025-26."""
    s = clean(season)
    m = re.search(r"(\d{4})\s*[-/–]\s*(\d{2,4})$", s)
    if m:
        start = int(m.group(1))
        tail = m.group(2)
        if len(tail) == 4:
            return int(tail)
        century = (start // 100) * 100
        candidate = century + int(tail)
        if candidate <= start:
            candidate += 100
        return candidate
    m = re.search(r"(\d{4})$", s)
    return int(m.group(1)) if m else None


def season_start_end(season):
    y = end_year(season)
    if not y: return None, None
    return y - 1, y


def fetch(url, cache_path):
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path.read_text(encoding="utf-8", errors="ignore")
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    cache_path.write_text(r.text, encoding="utf-8")
    time.sleep(0.35)
    return r.text


def flatten_cols(cols):
    out=[]
    for c in cols:
        if isinstance(c, tuple):
            out.append(" | ".join(str(x).strip() for x in c if str(x).strip() and str(x).lower() != "nan"))
        else: out.append(str(c).strip())
    return out


def find_standings_table(html):
    tables=[]
    try: tables = pd.read_html(io.StringIO(html))
    except Exception: pass
    candidates=[]
    for t in tables:
        cols=[c.lower() for c in flatten_cols(t.columns)]
        joined=" | ".join(cols)
        has_team=any(c in ("team","tm","team name","team_name") or c.endswith("| team") for c in cols)
        has_w=any(c in ("w","wins","win") or c.endswith("| w") for c in cols)
        has_l=any(c in ("l","losses","loss") or c.endswith("| l") for c in cols)
        has_rank=any(c in ("rk","rank","seed","no.","no") or "rank" in c or "seed" in c for c in cols)
        if has_team and has_w and has_l and has_rank: candidates.append(t)
    return candidates


def parse_land_standings(html, season):
    rows=[]
    for t in find_standings_table(html):
        cols=flatten_cols(t.columns); low=[c.lower() for c in cols]
        def idx(names, contains=()):
            for n in names:
                if n in low: return low.index(n)
            for i,c in enumerate(low):
                if any(x in c for x in contains): return i
            return None
        ri=idx(["rk","rank","seed","no.","no"], ("rank","seed"))
        ti=idx(["team","tm","team name","team_name"], ("team",))
        wi=idx(["w","wins","win"], ())
        li=idx(["l","losses","loss"], ())
        ci=idx(["conference","conf"], ("conference","conf"))
        if ti is None or ri is None: continue
        for _,r in t.iterrows():
            tm=clean(r.iloc[ti])
            if not tm or tm.lower() in {"team","nan","none"}: continue
            try: seed=int(float(str(r.iloc[ri]).replace("*","")))
            except Exception: continue
            if not 1 <= seed <= 30: continue
            def num(i):
                if i is None:return None
                try:return float(str(r.iloc[i]).replace("%",""))
                except Exception:return None
            rows.append({
                "season":season,"team":tm,"team_key":key(tm),"seed":seed,
                "conference":clean(r.iloc[ci]) if ci is not None else None,
                "wins":num(wi),"losses":num(li),"source":"Land of Basketball"
            })
    # Avoid duplicate rows if a page repeats responsive/mobile tables.
    dedup={}
    for r in rows: dedup[(r["team_key"],r["seed"])]=r
    return list(dedup.values())


def normalize_round(raw):
    s=re.sub(r"\s+"," ",str(raw or "")).strip().lower()
    if "finals" in s and "conference" not in s and "division" not in s: return "FINALS"
    if "conference finals" in s or "division finals" in s: return "CONFERENCE FINALS"
    if "conference semifinals" in s or "division semifinals" in s: return "CONFERENCE SEMIFINALS"
    if "first round" in s: return "FIRST ROUND"
    if s == "semifinals" or "semifinal" in s: return "SEMIFINALS"
    if "quarterfinal" in s: return "QUARTERFINALS"
    return str(raw or "").strip().upper()


def parse_series_from_tables(html):
    found=[]
    tables=[]
    try: tables=pd.read_html(io.StringIO(html))
    except Exception: pass
    for t in tables:
        cols=[str(c).lower() for c in flatten_cols(t.columns)]
        for _,r in t.iterrows():
            vals=[clean(v) for v in r.tolist()]
            text=" | ".join(v for v in vals if v and v.lower()!="nan")
            m=re.search(r"(.+?)\s+over\s+(.+?)\s+\((\d+)\s*[-–]\s*(\d+)\)",text,re.I)
            if not m: continue
            # Find a likely round token anywhere in the row/table context.
            round_raw=next((v for v in vals if any(x in v.lower() for x in ["finals","round","semifinal","quarterfinal","division finals"])), "")
            found.append((round_raw,m.group(1),m.group(2),int(m.group(3)),int(m.group(4))))
    return found


def parse_series_from_text(html):
    soup=BeautifulSoup(html,"html.parser")
    text=soup.get_text("\n")
    lines=[clean(x) for x in text.splitlines() if clean(x)]
    found=[]; current_round=""
    round_pat=re.compile(r"^(Finals|(?:Eastern|Western) Conference Finals|(?:Eastern|Western) Conference Semifinals|(?:Eastern|Western) Conference First Round|(?:Eastern|Western) Division Finals|(?:Eastern|Western) Division Semifinals|Semifinals|First Round|Quarterfinals)$",re.I)
    for line in lines:
        if round_pat.match(line): current_round=line; continue
        m=re.search(r"(.+?)\s+over\s+(.+?)\s+\((\d+)\s*[-–]\s*(\d+)\)",line,re.I)
        if m:
            found.append((current_round,m.group(1),m.group(2),int(m.group(3)),int(m.group(4))))
    return found


def parse_bref_playoffs(html, season):
    series=parse_series_from_text(html)
    if not series: series=parse_series_from_tables(html)
    # Deduplicate identical series.
    uniq=[]; seen=set()
    for raw,winner,loser,ww,ll in series:
        rd=normalize_round(raw)
        if not rd: continue
        k=(rd,key(winner),key(loser),ww,ll)
        if k in seen: continue
        seen.add(k); uniq.append((rd,clean(winner),clean(loser),ww,ll))
    outcomes={}
    # Series order is generally early -> late on BRef, but we derive outcome
    # by the furthest round each team appears in, then mark Finals winner.
    rank={"QUARTERFINALS":1,"FIRST ROUND":1,"SEMIFINALS":2,"CONFERENCE SEMIFINALS":2,"CONFERENCE FINALS":3,"FINALS":4}
    for rd,winner,loser,ww,ll in uniq:
        rr=rank.get(rd,0)
        for tm,won in [(winner,True),(loser,False)]:
            k=key(tm); cur=outcomes.get(k)
            if not cur or rr > cur["round_rank"]:
                outcomes[k]={"team":tm,"team_key":k,"season":season,"playoff_round":rd,
                              "round_rank":rr,"series_wins":ww if won else ll,
                              "series_losses":ll if won else ww,"source":"Basketball-Reference"}
    # Exact Finals status is explicit on BRef and overrides generic round text.
    for rd,winner,loser,ww,ll in uniq:
        if rd=="FINALS":
            outcomes[key(winner)].update({"playoff_finish":"CHAMPION","playoff_status":"CHAMPION"})
            outcomes[key(loser)].update({"playoff_finish":"MADE FINALS","playoff_status":"MADE FINALS"})
    for o in outcomes.values():
        if "playoff_finish" not in o:
            o["playoff_finish"]=o["playoff_round"]
            o["playoff_status"]=o["playoff_round"]
    return list(outcomes.values()), uniq


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",type=int,default=None)
    ap.add_argument("--end",type=int,default=None)
    ap.add_argument("--delay",type=float,default=0.35)
    args=ap.parse_args()
    df=pd.read_csv(MASTER,low_memory=False)
    seasons=sorted({str(x) for x in df["Season"].dropna()},key=lambda s:end_year(s) or 0)
    seasons=[s for s in seasons if end_year(s) and (args.start is None or end_year(s)>=args.start) and (args.end is None or end_year(s)<=args.end)]
    result={"version":1,"sources":{
        "standings":"https://www.landofbasketball.com/yearbyyear/YYYY_YYYY_standings.htm",
        "playoffs":"https://www.basketball-reference.com/playoffs/NBA_YYYY.html"},"seasons":{}}
    failures=[]
    for season in seasons:
        sy,ey=season_start_end(season)
        print(f"[{season}] standings")
        sfile=RAW/f"land_{ey}.html"
        try:
            html=fetch(f"https://www.landofbasketball.com/yearbyyear/{sy}_{ey}_standings.htm",sfile)
            standings=parse_land_standings(html,season)
        except Exception as exc:
            print("  standings failed:",exc); standings=[]; failures.append((season,"standings",str(exc)))
        print(f"  seeds parsed: {len(standings)}")
        print(f"[{season}] playoffs")
        pfile=RAW/f"bref_playoffs_{ey}.html"
        try:
            html=fetch(f"https://www.basketball-reference.com/playoffs/NBA_{ey}.html",pfile)
            playoffs,series=parse_bref_playoffs(html,season)
        except Exception as exc:
            print("  playoffs failed:",exc); playoffs=[]; series=[]; failures.append((season,"playoffs",str(exc)))
        print(f"  playoff teams parsed: {len(playoffs)}, series: {len(series)}")
        by={}
        for r in standings: by.setdefault(r["team_key"],{}).update(r)
        for r in playoffs: by.setdefault(r["team_key"],{}).update(r)
        # Carry a clear status for teams that did not appear in playoff series.
        for r in by.values():
            if "playoff_finish" not in r:
                seed=r.get("seed")
                r["playoff_finish"]="MISSED PLAYOFFS"
                r["playoff_status"]="PLAY-IN / MISSED PLAYOFFS" if seed in (9,10) else "MISSED PLAYOFFS"
            r.pop("round_rank",None)
        result["seasons"][season]=list(by.values())
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,separators=(",",":"),ensure_ascii=False),encoding="utf-8")
    (OUT.with_name("team_competitive_context_v1_build_report.json")).write_text(json.dumps({"seasons":len(seasons),"failures":failures},indent=2),encoding="utf-8")
    print("WROTE",OUT)
    print("SEASONS",len(seasons),"FAILURES",len(failures))

if __name__=="__main__": main()
