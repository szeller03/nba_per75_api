"""NBA PER-75 — Team Competitive Context Builder V6

One-command, offline-first builder. Automatically discovers browser-exported
Land of Basketball standings bundle and Basketball-Reference series HTML in
common project locations. No network access is attempted by this builder.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
MASTER=ROOT/'data'/'nba_per75_team_master_enriched.csv'
OUT=ROOT/'local_api'/'cache'/'team_competitive_context_v6.json'
REPORT=ROOT/'local_api'/'cache'/'team_competitive_context_v6_build_report.json'

# Reuse V5 parser implementation without duplicating the large source layer.
V5=ROOT/'local_api'/'build_team_competitive_context_v5.py'
ns={'__file__': str(V5), '__name__': '_v5_embedded'}
exec(compile(V5.read_text(encoding='utf-8'),str(V5),'exec'),ns)
parse_land=ns['parse_land']; parse_bref=ns['parse_bref']; outcomes=ns['outcomes']; season_bounds=ns['season_bounds']; end_year=ns['end_year']; key=ns['key']; clean=ns['clean']

IGNORE_DIRS={'.git','node_modules','dist','build','__pycache__'}
def discover(root:Path, names):
    hits=[]
    for name in names:
        p=root/name
        if p.is_file(): hits.append(p)
    for base in [root/'local_api',root/'local_api'/'cache',root/'tools',root/'data',root]:
        if not base.exists(): continue
        try:
            for p in base.rglob('*'):
                if any(part in IGNORE_DIRS for part in p.parts): continue
                if p.is_file() and p.name in names: hits.append(p)
        except OSError: pass
    # stable unique order, newest first
    uniq={str(p.resolve()):p for p in hits}
    return sorted(uniq.values(),key=lambda p:p.stat().st_mtime,reverse=True)

def choose_file(label, candidates, explicit=None):
    if explicit:
        p=Path(explicit).expanduser().resolve()
        if not p.is_file():
            raise SystemExit(f'ERROR: {label} not found: {p}')
        return p
    if not candidates:
        raise SystemExit(f'ERROR: Could not find {label}. Put the browser export in local_api/cache/ and rerun.')
    if len(candidates)>1:
        print(f'[auto] {label}: using newest of {len(candidates)} candidates -> {candidates[0]}')
    else: print(f'[auto] {label}: {candidates[0]}')
    return candidates[0]

def main():
    ap=argparse.ArgumentParser(description='Build team competitive context from local browser exports only.')
    ap.add_argument('--land-bundle'); ap.add_argument('--bref-html'); ap.add_argument('--start',type=int); ap.add_argument('--end',type=int)
    args=ap.parse_args()
    land_path=choose_file('Land standings bundle',discover(ROOT,['land_standings_bundle.json']),args.land_bundle)
    bref_path=choose_file('Basketball-Reference series HTML',discover(ROOT,['series.html','series_history.html','bref_series.html']),args.bref_html)
    land=ns['load_land_bundle'](land_path); bref=parse_bref(bref_path.read_text(encoding='utf-8',errors='ignore'))
    df=pd.read_csv(MASTER,low_memory=False); seasons=sorted({str(x) for x in df['Season'].dropna()},key=lambda s:end_year(s) or 0)
    seasons=[s for s in seasons if end_year(s) and (args.start is None or end_year(s)>=args.start) and (args.end is None or end_year(s)<=args.end)]
    result={'version':6,'sources':{'standings':'Land of Basketball browser-exported source pages','playoffs':'Basketball-Reference browser-exported playoffs/series.html','acquisition':'offline browser exports; builder performs no network requests'},'seasons':{}}
    failures=[]; land_rows=finish_rows=land_ok=0
    for season in seasons:
        _,ey=season_bounds(season); print(f'[{season}] standings')
        html=land.get(season); standings=parse_land(html,season) if html else []
        if standings: land_ok+=1; land_rows+=len(standings)
        else: failures.append((season,'standings','missing or no rows in land bundle'))
        print(f'  seeds parsed: {len(standings)}')
        outs=outcomes(bref,ey); finish_rows+=len(outs)
        print(f'[{season}] playoffs'); print(f'  playoff teams parsed: {len(outs)}, series: {sum(1 for s in bref if s["year"]==ey)}')
        by={r['team_key']:dict(r) for r in standings}
        for k,r in outs.items(): by.setdefault(k,{}).update(r)
        for r in by.values():
            if 'playoff_finish' not in r:
                q=r.get('postseason_qualification'); r['playoff_finish']='PLAY-IN / MISSED PLAYOFFS' if q=='PLAY-IN' or r.get('seed') in (9,10) else 'MISSED PLAYOFFS'; r['playoff_status']=r['playoff_finish']
        result['seasons'][season]=list(by.values())
    meta={'seasons_requested':len(seasons),'standings_seasons_with_rows':land_ok,'standings_rows':land_rows,'playoff_finish_rows':finish_rows,'failures':failures,'land_bundle':str(land_path),'bref_html':str(bref_path)}
    result['metadata']=meta; OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8'); REPORT.write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print('\nBUILD COMPLETE'); print('SEASONS',len(seasons)); print('STANDINGS SEASONS',land_ok); print('SEED ROWS',land_rows); print('PLAYOFF FINISH ROWS',finish_rows); print('FAILURES',len(failures)); print('WROTE',OUT); print('WROTE',REPORT)
    if land_ok < len(seasons):
        print('\nWARNING: standings are incomplete; do not treat this cache as authoritative.')
        return 2
    if not finish_rows:
        print('\nWARNING: no playoff finish rows were parsed; do not treat this cache as authoritative.')
        return 3
    return 0
if __name__=='__main__': sys.exit(main())
