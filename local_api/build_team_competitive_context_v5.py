"""NBA PER-75 — Team Competitive Context Builder V5

Offline-first source ingestion for team seed + playoff finish.

V5 deliberately removes network dependency from the build itself.  Direct
requests to Land of Basketball and Basketball-Reference have been returning
403/429/401 in the user's environment, so V5 accepts browser-exported source
bundles instead of trying more proxies or retry loops.

Inputs:
  --land-bundle PATH  JSON exported by tools/export_land_standings_bundle.html
  --bref-html PATH    locally saved Basketball-Reference series.html

The output schema remains compatible with the V4 competitive-context cache.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[0].parent
MASTER = ROOT / 'data' / 'nba_per75_team_master_enriched.csv'
OUT = ROOT / 'local_api' / 'cache' / 'team_competitive_context_v5.json'
REPORT = ROOT / 'local_api' / 'cache' / 'team_competitive_context_v5_build_report.json'

ALIASES = {
    'okc':'oklahomacitythunder','oklahomacity':'oklahomacitythunder','sea':'seattlesupersonics','seattle':'seattlesupersonics',
    'nj':'brooklynnets','newjersey':'brooklynnets','bkn':'brooklynnets','njn':'brooklynnets',
    'la':'losangeleslakers','lal':'losangeleslakers','gs':'goldenstatewarriors','gsw':'goldenstatewarriors',
    'ny':'newyorkknicks','nyk':'newyorkknicks','phx':'phoenixsuns','pho':'phoenixsuns',
    'sas':'sanantoniospurs','sa':'sanantoniospurs','uta':'utahjazz','was':'washingtonwizards','wsh':'washingtonwizards',
    'nop':'neworleanspelicans','no':'neworleanspelicans','nohl':'neworleanspelicans','lac':'losangelesclippers',
    'van':'memphisgrizzlies','kck':'sacramentokings','kco':'sacramentokings','cin':'sacramentokings',
    'sdc':'losangelesclippers','sd':'losangelesclippers','buf':'losangelesclippers','stl':'atlantahawks','mlh':'atlantahawks','tri':'atlantahawks',
    'phw':'goldenstatewarriors','sfw':'goldenstatewarriors','chp':'washingtonwizards','chz':'washingtonwizards','blb':'washingtonwizards','cap':'washingtonwizards','wsb':'washingtonwizards',
    'ftw':'detroitpistons','syr':'philadelphia76ers','roc':'sacramentokings','ino':'indianapacers','ind':'indianapacers','phi':'philadelphia76ers','phl':'philadelphia76ers',
    'por':'portlandtrailblazers','den':'denvernuggets','min':'minnesotatimberwolves','mil':'milwaukeebucks','chi':'chicagobulls','bos':'bostonceltics','cle':'clevelandcavaliers','det':'detroitpistons','atl':'atlantahawks','hou':'houstonrockets','mem':'memphisgrizzlies','orl':'orlandomagic','sac':'sacramentokings','tor':'torontoraptors','indianapacers':'indianapacers'
}
ALIASES['sas']='sanantoniospurs'
ALIASES['sanantoniospurs']='sanantoniospurs'
# Correct canonical spelling after the compact historical alias table above.
ALIASES['sas']='sanantoniospurs'; ALIASES['sanantonio']='sanantoniospurs'; ALIASES['sanantoniospurs']='sanantoniospurs'

ROUND_RANK={'DIVISION SEMIFINALS':1,'DIVISION SEMIFINAL':1,'FIRST ROUND':1,'CONFERENCE FIRST ROUND':1,'QUARTERFINALS':1,
'DIVISION FINALS':2,'DIVISION FINAL':2,'CONFERENCE SEMIFINALS':2,'CONFERENCE SEMIFINAL':2,'SEMIFINALS':2,
'CONFERENCE FINALS':3,'CONFERENCE FINAL':3,'FINALS':4}

def clean(x): return re.sub(r'\s+',' ',str(x or '').replace('\xa0',' ')).strip()
def key(x):
    s=re.sub(r'[^a-z0-9]','',clean(x).lower()); return ALIASES.get(s,s)
def end_year(season):
    s=clean(season); m=re.search(r'(\d{4})\s*[-/–]\s*(\d{2,4})$',s)
    if m:
        start,tail=int(m.group(1)),m.group(2); return int(tail) if len(tail)==4 else ((start//100)*100+int(tail)+(100 if int(tail)+(start//100)*100<=start else 0))
    m=re.search(r'(\d{4})$',s); return int(m.group(1)) if m else None
def season_bounds(season):
    y=end_year(season); return (y-1,y) if y else (None,None)
def rank_from_text(x):
    m=re.match(r'^(\d{1,2})\s*\.?\s*$',clean(x)); return int(m.group(1)) if m else None

def parse_land(html, season):
    soup=BeautifulSoup(html,'html.parser'); rows=[]; seen=set()
    for table in soup.find_all('table'):
        # heading immediately before table is enough for the site's conference/division layout.
        conf=None
        node=table
        for _ in range(10):
            node=node.find_previous(['h2','h3','h4','h5'])
            if not node: break
            t=clean(node.get_text(' ')).lower()
            if 'western conference' in t or 'western division' in t: conf='Western'; break
            if 'eastern conference' in t or 'eastern division' in t: conf='Eastern'; break
        for tr in table.find_all('tr'):
            cells=tr.find_all(['th','td']); vals=[clean(c.get_text(' ')) for c in cells]
            if len(vals)<4: continue
            seed=rank_from_text(vals[0]); team=vals[1]
            if seed is None:
                m=re.match(r'^(\d{1,2})\.?\s+(.+)$',team)
                if m: seed=int(m.group(1)); team=clean(m.group(2))
            if seed is None or not 1<=seed<=30 or not team or team.lower() in {'team','teams'}: continue
            tk=key(team)
            sig=(tk,seed,conf)
            if sig in seen: continue
            wins=losses=None
            try: wins=int(re.sub(r'[^0-9]','',vals[2])); losses=int(re.sub(r'[^0-9]','',vals[3]))
            except: pass
            rowtxt=' '.join(vals); q='PLAY-IN' if re.search(r'\bpi\b',rowtxt,re.I) else ('PLAYOFFS' if re.search(r'\bp\b',rowtxt,re.I) else '')
            rows.append({'season':season,'team':team,'team_key':tk,'seed':seed,'conference':conf,'wins':wins,'losses':losses,'postseason_qualification':q,'source':'Land of Basketball'})
            seen.add(sig)
    return rows

def normalize_round(raw):
    s=clean(raw).lower(); s=re.sub(r'\b(eastern|western)\s+','',s); s=re.sub(r'\bconf\b','conference',s)
    if s in {'final','finals'}: return 'FINALS'
    if 'conference finals' in s: return 'CONFERENCE FINALS'
    if 'conference semifinals' in s: return 'CONFERENCE SEMIFINALS'
    if 'conference first round' in s or 'first round' in s: return 'FIRST ROUND'
    if 'division finals' in s: return 'DIVISION FINALS'
    if 'division semifinals' in s: return 'DIVISION SEMIFINALS'
    if 'semifinal' in s: return 'SEMIFINALS'
    if 'quarterfinal' in s: return 'QUARTERFINALS'
    return clean(raw).upper()

def parse_bref(html):
    series=[]
    for t in pd.read_html(html):
        if isinstance(t.columns,pd.MultiIndex): t.columns=[' | '.join(str(x) for x in c if str(x).lower()!='nan').strip() for c in t.columns]
        else: t.columns=[str(c) for c in t.columns]
        cols=[clean(c).lower() for c in t.columns]
        def fc(*names):
            for n in names:
                for i,c in enumerate(cols):
                    if c==n or c.endswith('| '+n) or n in c: return i
            return None
        yi,li,ri=fc('yr','year'),fc('lg','league'),fc('series','round')
        if None in (yi,li,ri): continue
        team_cols=[i for i,c in enumerate(cols) if c=='team' or c.endswith('| team')]
        if len(team_cols)<2: continue
        for _,row in t.iterrows():
            lg=clean(row.iloc[li]).upper()
            if lg and lg!='NBA': continue
            m=re.search(r'(\d{4})',clean(row.iloc[yi]));
            if not m: continue
            w=clean(row.iloc[team_cols[0]]); l=clean(row.iloc[team_cols[1]])
            if not w or not l or w.lower()=='nan' or l.lower()=='nan': continue
            series.append({'year':int(m.group(1)),'league':'NBA','round':normalize_round(row.iloc[ri]),'winner':re.sub(r'\s*\(\d+\)\s*$','',w),'loser':re.sub(r'\s*\(\d+\)\s*$','',l)})
    out=[]; seen=set()
    for s in series:
        sig=(s['year'],s['round'],s['winner'],s['loser'])
        if sig not in seen: out.append(s); seen.add(sig)
    return out

def outcomes(series,year):
    by={}
    ss=[s for s in series if s['year']==year and s.get('league','NBA')=='NBA']
    for s in ss:
        rr=ROUND_RANK.get(s['round'],0)
        for tm in (s['winner'],s['loser']):
            k=key(tm)
            if not k: continue
            if k not in by or rr>by[k].get('_rank',0): by[k]={'season_end_year':year,'team':tm,'team_key':k,'playoff_round':s['round'],'_rank':rr,'source':'Basketball-Reference'}
    for s in ss:
        if s['round']=='FINALS':
            wk,lk=key(s['winner']),key(s['loser'])
            if wk in by: by[wk].update(playoff_finish='CHAMPION',playoff_status='CHAMPION')
            if lk in by: by[lk].update(playoff_finish='MADE FINALS',playoff_status='MADE FINALS')
    for v in by.values():
        v.setdefault('playoff_finish',v.get('playoff_round','UNKNOWN')); v.setdefault('playoff_status',v['playoff_finish']); v.pop('_rank',None)
    return by

def load_land_bundle(path):
    obj=json.loads(Path(path).read_text(encoding='utf-8'))
    # Supported formats: {"pages":[{"season":"1951-52","html":"..."}]} or {season:html}.
    pages=obj.get('pages',obj) if isinstance(obj,dict) else obj
    out={}
    if isinstance(pages,list):
        for p in pages:
            if isinstance(p,dict) and p.get('season') and p.get('html'): out[str(p['season'])]=p['html']
    elif isinstance(pages,dict):
        for k,v in pages.items():
            if isinstance(v,str): out[str(k)]=v
            elif isinstance(v,dict) and v.get('html'): out[str(k)]=v['html']
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--land-bundle',required=True); ap.add_argument('--bref-html',required=True); ap.add_argument('--start',type=int); ap.add_argument('--end',type=int); args=ap.parse_args()
    df=pd.read_csv(MASTER,low_memory=False); seasons=sorted({str(x) for x in df['Season'].dropna()},key=lambda s:end_year(s) or 0)
    seasons=[s for s in seasons if end_year(s) and (args.start is None or end_year(s)>=args.start) and (args.end is None or end_year(s)<=args.end)]
    land=load_land_bundle(args.land_bundle); bref=parse_bref(Path(args.bref_html).read_text(encoding='utf-8',errors='ignore'))
    result={'version':5,'sources':{'standings':'Land of Basketball browser-exported source pages','playoffs':'Basketball-Reference browser-exported playoffs/series.html','acquisition':'offline browser exports; no proxy/retry dependency'},'seasons':{}}
    failures=[]; land_rows=finish_rows=land_ok=0
    for season in seasons:
        sy,ey=season_bounds(season); print(f'[{season}] standings')
        html=land.get(season)
        standings=parse_land(html,season) if html else []
        if standings: land_ok+=1; land_rows+=len(standings)
        else: failures.append((season,'standings','missing or no rows in land bundle'))
        print(f'  seeds parsed: {len(standings)}')
        outs=outcomes(bref,ey); finish_rows+=len(outs); print(f'[{season}] playoffs'); print(f'  playoff teams parsed: {len(outs)}, series: {sum(1 for s in bref if s["year"]==ey)}')
        by={r['team_key']:dict(r) for r in standings}
        for k,r in outs.items(): by.setdefault(k,{}).update(r)
        for r in by.values():
            if 'playoff_finish' not in r:
                q=r.get('postseason_qualification')
                r['playoff_finish']='PLAY-IN / MISSED PLAYOFFS' if q=='PLAY-IN' or r.get('seed') in (9,10) else 'MISSED PLAYOFFS'; r['playoff_status']=r['playoff_finish']
        result['seasons'][season]=list(by.values())
    meta={'seasons_requested':len(seasons),'standings_seasons_with_rows':land_ok,'standings_rows':land_rows,'playoff_finish_rows':finish_rows,'failures':failures,'land_bundle':str(args.land_bundle),'bref_html':str(args.bref_html)}
    result['metadata']=meta; OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8'); REPORT.write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print('\nBUILD COMPLETE'); print('SEASONS',len(seasons)); print('STANDINGS SEASONS',land_ok); print('SEED ROWS',land_rows); print('PLAYOFF FINISH ROWS',finish_rows); print('FAILURES',len(failures)); print('WROTE',OUT); print('WROTE',REPORT)
if __name__=='__main__': main()
