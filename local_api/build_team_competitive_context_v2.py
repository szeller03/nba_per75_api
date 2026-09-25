"""NBA PER-75 — Team Competitive Context Builder V2

Builds regular-season seed/context from Land of Basketball season standings pages
and playoff finish from Basketball-Reference's all-time playoff series table.

Key improvements over V1:
- Land of Basketball parser reads the rank embedded in the Team cell (e.g. `1.`),
  which is how its conference tables are actually structured.
- Basketball-Reference is fetched primarily from the single `playoffs/series.html`
  history table, avoiding 75 separate playoff-page requests and reducing 429s.
- Requests are cached, retried with exponential backoff, and failures are recorded
  without aborting the whole build.
- Existing successful raw pages can be reused; reruns are resumable.

Run from project root:
  python local_api/build_team_competitive_context_v2.py

Optional:
  --start 1980 --end 2026
  --delay 1.5
  --retry 5
  --series-url https://www.basketball-reference.com/playoffs/series.html
"""
from __future__ import annotations
import argparse, json, random, re, time, io
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[0].parent
MASTER = ROOT / "data" / "nba_per75_team_master_enriched.csv"
OUT = ROOT / "local_api" / "cache" / "team_competitive_context_v2.json"
REPORT = OUT.with_name("team_competitive_context_v2_build_report.json")
RAW = ROOT / "local_api" / "cache" / "team_competitive_sources_v2"
RAW.mkdir(parents=True, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36 NBA-PER-75 historical reference builder/2.0"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

ALIASES = {
    "okc":"oklahomacitythunder","seattle":"seattlesupersonics","nj":"brooklynnets",
    "newjersey":"brooklynnets","la":"losangeleslakers","gs":"goldenstatewarriors",
    "gsw":"goldenstatewarriors","ny":"newyorkknicks","nyk":"newyorkknicks",
    "phx":"phoenixsuns","pho":"phoenixsuns","sas":"sanantoniospurs","sa":"sanantoniospurs",
    "uta":"utahjazz","was":"washingtonwizards","wsh":"washingtonwizards",
    "nop":"neworleanspelicans","no":"neworleanspelicans","nohl":"neworleanspelicans",
    "lac":"losangelesclippers","lal":"losangeleslakers","van":"memphisgrizzlies",
    "sea":"seattlesupersonics","njn":"brooklynnets","kck":"sacramentokings",
    "kco":"sacramentokings","cin":"sacramentokings","sdc":"losangelesclippers",
    "sd":"losangelesclippers","buf":"losangelesclippers","stl":"atlantahawks",
    "mlh":"atlantahawks","tri":"atlantahawks","phw":"goldenstatewarriors",
    "sfw":"goldenstatewarriors","chp":"washingtonwizards","chz":"washingtonwizards",
    "blb":"washingtonwizards","cap":"washingtonwizards","wsb":"washingtonwizards",
    "ftw":"detroitpistons","syr":"philadelphia76ers","roc":"sacramentokings",
    "ino":"indianapolispacers","ind":"indianapacers","phi":"philadelphia76ers",
    "phl":"philadelphia76ers","bkn":"brooklynnets","por":"portlandtrailblazers",
}

ROUND_RANK = {
    "DIVISION SEMIFINALS":1, "DIVISION SEMIFINAL":1,
    "CONFERENCE FIRST ROUND":1, "FIRST ROUND":1, "QUARTERFINALS":1,
    "DIVISION FINALS":2, "DIVISION FINAL":2,
    "CONFERENCE SEMIFINALS":2, "CONFERENCE SEMIFINAL":2, "SEMIFINALS":2,
    "CONFERENCE FINALS":3, "CONFERENCE FINAL":3,
    "FINALS":4,
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
        if len(tail) == 4: return int(tail)
        candidate = (start // 100) * 100 + int(tail)
        if candidate <= start: candidate += 100
        return candidate
    m = re.search(r"(\d{4})$", s)
    return int(m.group(1)) if m else None


def season_bounds(season):
    y=end_year(season)
    return (y-1,y) if y else (None,None)


def session_get(url, timeout=45):
    s=requests.Session()
    s.headers.update(HEADERS)
    return s.get(url, timeout=timeout)


def fetch_cached(url, path, delay=1.0, retries=5):
    if path.exists() and path.stat().st_size > 0:
        return path.read_text(encoding="utf-8", errors="ignore"), {"cached":True,"status":200,"attempts":0}
    last=None
    for attempt in range(1,retries+1):
        try:
            r=session_get(url)
            status=r.status_code
            if status == 429:
                wait=max(delay*(2**(attempt-1)), 4.0) + random.uniform(0.25,1.25)
                last=f"HTTP 429; retrying in {wait:.1f}s"
                print(f"    {last}")
                time.sleep(wait)
                continue
            r.raise_for_status()
            text=r.text
            path.write_text(text,encoding="utf-8")
            time.sleep(delay+random.uniform(0.1,0.35))
            return text,{"cached":False,"status":status,"attempts":attempt}
        except Exception as exc:
            last=str(exc)
            if attempt < retries:
                wait=max(delay*(2**(attempt-1)),2.0)+random.uniform(0.25,1.0)
                print(f"    fetch attempt {attempt}/{retries} failed: {exc}; retrying in {wait:.1f}s")
                time.sleep(wait)
    raise RuntimeError(last or "fetch failed")


def rank_from_text(text):
    m=re.match(r"^(\d{1,2})\s*\.?\s*$",clean(text))
    return int(m.group(1)) if m else None


def parse_land_standings(html, season):
    soup=BeautifulSoup(html,"html.parser")
    rows=[]
    seen=set()
    # Land of Basketball's conference tables encode the seed as the first cell
    # (e.g. `1.`) and the team name as the next cell. Division tables repeat the
    # teams, so we retain the first occurrence of each team on the page.
    for table in soup.find_all("table"):
        table_text=clean(table.get_text(" "))
        if "Team" not in table_text or not re.search(r"\bW\b",table_text) or not re.search(r"\bL\b",table_text):
            continue
        # Find nearest heading before this table to identify conference.
        conference=None
        node=table
        for _ in range(12):
            node=node.find_previous(["h1","h2","h3","h4","h5","h6"])
            if not node: break
            ht=clean(node.get_text(" "))
            if re.search(r"Western Conference",ht,re.I): conference="Western"
            elif re.search(r"Eastern Conference",ht,re.I): conference="Eastern"
            if conference: break
        for tr in table.find_all("tr"):
            cells=tr.find_all(["th","td"])
            if len(cells)<3: continue
            vals=[clean(c.get_text(" ")) for c in cells]
            seed=rank_from_text(vals[0])
            if seed is None or not (1<=seed<=30): continue
            team=re.sub(r"^\d{1,2}\s*\.\s*", "", vals[1]).strip()
            if not team or team.lower() in {"team","teams"}: continue
            tk=key(team)
            if tk in seen: continue
            # Locate W/L by header position when possible; for this source they
            # are normally cells 2 and 3.
            wins=losses=None
            for label,val in zip(vals[2:], vals[2:]):
                pass
            try:
                wins=float(re.sub(r"[^0-9.]","",vals[2])) if vals[2] else None
                losses=float(re.sub(r"[^0-9.]","",vals[3])) if len(vals)>3 else None
            except Exception:
                pass
            qualification=""
            row_text=" ".join(vals)
            if re.search(r"\bpi\b",row_text): qualification="PLAY-IN"
            elif re.search(r"\bp\b",row_text): qualification="PLAYOFFS"
            rows.append({"season":season,"team":team,"team_key":tk,"seed":seed,
                         "conference":conference,"wins":wins,"losses":losses,
                         "postseason_qualification":qualification,
                         "source":"Land of Basketball"})
            seen.add(tk)
    return rows


def normalize_round(raw):
    s=clean(raw).lower()
    s=re.sub(r"\b(eastern|western)\s+", "", s)
    s=re.sub(r"\bconf\b", "conference", s)
    s=re.sub(r"\s+", " ", s).strip()
    if "final" == s or s == "finals": return "FINALS"
    if "conference finals" in s: return "CONFERENCE FINALS"
    if "conference semifinals" in s: return "CONFERENCE SEMIFINALS"
    if "conference first round" in s: return "FIRST ROUND"
    if "first round" in s: return "FIRST ROUND"
    if "division finals" in s: return "DIVISION FINALS"
    if "division semifinals" in s: return "DIVISION SEMIFINALS"
    if "semifinal" in s: return "SEMIFINALS"
    if "quarterfinal" in s: return "QUARTERFINALS"
    return clean(raw).upper()


def parse_bref_series_history(html):
    soup=BeautifulSoup(html,"html.parser")
    all_series=[]
    # Prefer the table whose headers clearly identify Year/Round/Winner/Loser.
    for table in soup.find_all("table"):
        trs=table.find_all("tr")
        if not trs: continue
        header=[]
        for tr in trs[:3]:
            h=[clean(c.get_text(" ")).lower() for c in tr.find_all(["th","td"])]
            if h: header=h; break
        joined=" | ".join(header)
        if "year" not in joined or "winner" not in joined or "loser" not in joined:
            continue
        # Use pandas on the individual table where possible; fallback to cells.
        try:
            t=pd.read_html(io.StringIO(str(table)))[0]
            cols=[]
            for c in t.columns:
                if isinstance(c,tuple): cols.append(" | ".join(str(x) for x in c if str(x).lower()!="nan"))
                else: cols.append(str(c))
            low=[c.lower() for c in cols]
            def findcol(*names):
                # Exact header matches first; this prevents `w` from matching
                # the word `winner` and `l` from matching `loser`.
                for n in names:
                    for i,c in enumerate(low):
                        if c.strip()==n or c.endswith("| "+n): return i
                for n in names:
                    for i,c in enumerate(low):
                        if n in c: return i
                return None
            yi=findcol("year"); ri=findcol("round"); wi=findcol("winner"); li=findcol("loser")
            wni=findcol("w"); lni=findcol("l")
            if None not in (yi,ri,wi,li):
                for _,row in t.iterrows():
                    ymatch=re.search(r"(\d{4})",clean(row.iloc[yi]))
                    if not ymatch: continue
                    y=int(ymatch.group(1)); rd=normalize_round(row.iloc[ri]); winner=clean(row.iloc[wi]); loser=clean(row.iloc[li])
                    if not winner or not loser: continue
                    def intval(i):
                        if i is None:return None
                        m=re.search(r"\d+",clean(row.iloc[i])); return int(m.group()) if m else None
                    all_series.append({"year":y,"round":rd,"winner":winner,"loser":loser,"winner_w":intval(wni),"loser_w":intval(lni)})
                if all_series: return all_series
        except Exception:
            pass
    # Generic HTML fallback: locate header indexes and parse each row.
    for table in soup.find_all("table"):
        rows=table.find_all("tr")
        header_idx=None; idx={}
        for j,tr in enumerate(rows[:5]):
            hs=[clean(c.get_text(" ")).lower() for c in tr.find_all(["th","td"])]
            for wanted in ("year","round","winner","loser"):
                if wanted in hs: idx[wanted]=hs.index(wanted)
            if len(idx)>=4: header_idx=j; break
        if header_idx is None: continue
        for tr in rows[header_idx+1:]:
            vals=[clean(c.get_text(" ")) for c in tr.find_all(["th","td"])]
            if len(vals)<=max(idx.values()): continue
            m=re.search(r"(\d{4})",vals[idx["year"]])
            if not m: continue
            winner=vals[idx["winner"]]; loser=vals[idx["loser"]]
            if winner and loser:
                all_series.append({"year":int(m.group(1)),"round":normalize_round(vals[idx["round"]]),"winner":winner,"loser":loser,"winner_w":None,"loser_w":None})
        if all_series: return all_series
    return []


def playoff_outcomes(series, season_year):
    by={}
    season_series=[s for s in series if s["year"]==season_year]
    for s in season_series:
        rd=s["round"]; rr=ROUND_RANK.get(rd,0)
        for tm,won in ((s["winner"],True),(s["loser"],False)):
            k=key(tm)
            if not k: continue
            cur=by.get(k)
            if cur is None or rr>cur["round_rank"]:
                by[k]={"season_end_year":season_year,"team":tm,"team_key":k,
                       "playoff_round":rd,"round_rank":rr,
                       "series_wins":s.get("winner_w") if won else s.get("loser_w"),
                       "series_losses":s.get("loser_w") if won else s.get("winner_w"),
                       "source":"Basketball-Reference"}
    for s in season_series:
        if s["round"]=="FINALS":
            wk,lk=key(s["winner"]),key(s["loser"])
            if wk in by: by[wk].update(playoff_finish="CHAMPION",playoff_status="CHAMPION")
            if lk in by: by[lk].update(playoff_finish="MADE FINALS",playoff_status="MADE FINALS")
    for o in by.values():
        if "playoff_finish" not in o:
            o["playoff_finish"]=o["playoff_round"]
            o["playoff_status"]=o["playoff_round"]
        o.pop("round_rank",None)
    return by


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",type=int,default=None)
    ap.add_argument("--end",type=int,default=None)
    ap.add_argument("--delay",type=float,default=1.0)
    ap.add_argument("--retry",type=int,default=5)
    ap.add_argument("--series-url",default="https://www.basketball-reference.com/playoffs/series.html")
    args=ap.parse_args()

    df=pd.read_csv(MASTER,low_memory=False)
    seasons=sorted({str(x) for x in df["Season"].dropna()},key=lambda s:end_year(s) or 0)
    seasons=[s for s in seasons if end_year(s) and (args.start is None or end_year(s)>=args.start) and (args.end is None or end_year(s)<=args.end)]

    failures=[]
    result={"version":2,"sources":{"standings":"https://www.landofbasketball.com/yearbyyear/YYYY_YYYY_standings.htm","playoffs":args.series_url},"seasons":{}}

    # One B-Ref request for the complete series history.
    series_file=RAW/"bref_playoff_series_history.html"
    print("[Basketball-Reference] playoff series history")
    try:
        series_html,meta=fetch_cached(args.series_url,series_file,args.delay,args.retry)
        series=parse_bref_series_history(series_html)
        print(f"  series parsed: {len(series)}")
        if not series: failures.append(("ALL","playoffs","series history parsed 0 rows"))
    except Exception as exc:
        print("  playoffs history failed:",exc); series=[]; failures.append(("ALL","playoffs",str(exc)))

    for season in seasons:
        sy,ey=season_bounds(season)
        print(f"[{season}] standings")
        sfile=RAW/f"land_{ey}.html"
        try:
            html,meta=fetch_cached(f"https://www.landofbasketball.com/yearbyyear/{sy}_{ey}_standings.htm",sfile,args.delay,args.retry)
            standings=parse_land_standings(html,season)
        except Exception as exc:
            print("  standings failed:",exc); standings=[]; failures.append((season,"standings",str(exc)))
        print(f"  seeds parsed: {len(standings)}")
        outcomes=playoff_outcomes(series,ey)
        print(f"[{season}] playoffs")
        print(f"  playoff teams parsed: {len(outcomes)}, series: {sum(1 for s in series if s['year']==ey)}")

        by={}
        for r in standings: by[r["team_key"]]=dict(r)
        for k,r in outcomes.items(): by.setdefault(k,{}).update(r)
        for r in by.values():
            if "playoff_finish" not in r:
                q=r.get("postseason_qualification")
                if q=="PLAY-IN" or r.get("seed") in (9,10):
                    r["playoff_finish"]="PLAY-IN / MISSED PLAYOFFS"; r["playoff_status"]="PLAY-IN / MISSED PLAYOFFS"
                else:
                    r["playoff_finish"]="MISSED PLAYOFFS"; r["playoff_status"]="MISSED PLAYOFFS"
        result["seasons"][season]=list(by.values())

    # Validation report
    seed_count=sum(1 for rows in result["seasons"].values() for r in rows if r.get("seed") is not None)
    finish_count=sum(1 for rows in result["seasons"].values() for r in rows if r.get("playoff_finish"))
    result["validation"]={"season_count":len(seasons),"seed_rows":seed_count,"finish_rows":finish_count,
                           "failures":len(failures),"notes":["Seed is parsed from Land of Basketball conference standings, not PER-75 Rk.","Playoff finish is derived from Basketball-Reference all-time playoff series history."]}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,separators=(",",":"),ensure_ascii=False),encoding="utf-8")
    REPORT.write_text(json.dumps({"seasons":len(seasons),"seed_rows":seed_count,"finish_rows":finish_count,"failures":failures},indent=2),encoding="utf-8")
    print("WROTE",OUT)
    print("SEASONS",len(seasons),"FAILURES",len(failures))
    print("SEED ROWS",seed_count,"FINISH ROWS",finish_count)

if __name__=="__main__": main()
