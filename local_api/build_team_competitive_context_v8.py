"""NBA PER-75 — Team Competitive Context Builder V8

Browser-native acquisition. No requests/proxies/API keys and no manual source
bundles. Uses an installed Chrome/Edge browser to fetch the public source pages,
then parses and caches the HTML locally before building the competitive-context
cache.
"""
from __future__ import annotations
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time, io, urllib.request, urllib.error
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
MASTER=ROOT/'data'/'nba_per75_team_master_enriched.csv'
CACHE=ROOT/'local_api'/'cache'/'team_competitive_context_v8_sources'
OUT=ROOT/'local_api'/'cache'/'team_competitive_context_v8.json'
REPORT=ROOT/'local_api'/'cache'/'team_competitive_context_v8_build_report.json'

ALIASES={'oklahomacity':'oklahomacitythunder','okc':'oklahomacitythunder','sea':'seattlesupersonics','seattle':'seattlesupersonics','nj':'brooklynnets','newjersey':'brooklynnets','bkn':'brooklynnets','njn':'brooklynnets','la':'losangeleslakers','lal':'losangeleslakers','gs':'goldenstatewarriors','gsw':'goldenstatewarriors','ny':'newyorkknicks','nyk':'newyorkknicks','phx':'phoenixsuns','pho':'phoenixsuns','sas':'sanantoniospurs','sa':'sanantoniospurs','uta':'utahjazz','was':'washingtonwizards','wsh':'washingtonwizards','nop':'neworleanspelicans','no':'neworleanspelicans','lac':'losangelesclippers','van':'memphisgrizzlies','kck':'sacramentokings','kco':'sacramentokings','cin':'sacramentokings','sdc':'losangelesclippers','sd':'losangelesclippers','buf':'losangelesclippers','stl':'atlantahawks','mlh':'atlantahawks','tri':'atlantahawks','phw':'goldenstatewarriors','sfw':'goldenstatewarriors','chp':'washingtonwizards','chz':'washingtonwizards','blb':'washingtonwizards','cap':'washingtonwizards','wsb':'washingtonwizards','ftw':'detroitpistons','syr':'philadelphia76ers','roc':'sacramentokings','ino':'indianapacers','ind':'indianapacers','phi':'philadelphia76ers','phl':'philadelphia76ers','por':'portlandtrailblazers','den':'denvernuggets','min':'minnesotatimberwolves','mil':'milwaukeebucks','chi':'chicagobulls','bos':'bostonceltics','cle':'clevelandcavaliers','det':'detroitpistons','atl':'atlantahawks','hou':'houstonrockets','mem':'memphisgrizzlies','orl':'orlandomagic','sac':'sacramentokings','tor':'torontoraptors','indianapacers':'indianapacers'}
ROUND_RANK={'DIVISION SEMIFINALS':1,'DIVISION SEMIFINAL':1,'FIRST ROUND':1,'CONFERENCE FIRST ROUND':1,'QUARTERFINALS':1,'DIVISION FINALS':2,'DIVISION FINAL':2,'CONFERENCE SEMIFINALS':2,'CONFERENCE SEMIFINAL':2,'SEMIFINALS':2,'CONFERENCE FINALS':3,'CONFERENCE FINAL':3,'FINALS':4}

def clean(x): return re.sub(r'\s+',' ',str(x or '').replace('\xa0',' ')).strip()
def key(x): return ALIASES.get(re.sub(r'[^a-z0-9]','',clean(x).lower()),re.sub(r'[^a-z0-9]','',clean(x).lower()))
def end_year(s):
 s=clean(s); m=re.search(r'(\d{4})\s*[-/–]\s*(\d{2,4})$',s)
 if m:
  a=int(m.group(1)); b=int(m.group(2)); return b if len(m.group(2))==4 else (a//100)*100+b+(100 if (a//100)*100+b<=a else 0)
 m=re.search(r'(\d{4})$',s); return int(m.group(1)) if m else None
def season_bounds(s): y=end_year(s); return (y-1,y) if y else (None,None)
def rank_from_text(x):
 m=re.match(r'^(\d{1,2})\s*\.?\s*$',clean(x)); return int(m.group(1)) if m else None

def parse_land(html,season):
 soup=BeautifulSoup(html,'html.parser'); rows=[]; seen=set()
 for table in soup.find_all('table'):
  conf=None; node=table
  for _ in range(10):
   node=node.find_previous(['h2','h3','h4','h5'])
   if not node: break
   t=clean(node.get_text(' ')).lower()
   if 'western conference' in t or 'western division' in t: conf='Western'; break
   if 'eastern conference' in t or 'eastern division' in t: conf='Eastern'; break
  for tr in table.find_all('tr'):
   vals=[clean(c.get_text(' ')) for c in tr.find_all(['th','td'])]
   if len(vals)<4: continue
   seed=rank_from_text(vals[0]); team=vals[1]
   if seed is None:
    m=re.match(r'^(\d{1,2})\.?\s+(.+)$',team)
    if m: seed=int(m.group(1)); team=clean(m.group(2))
   if seed is None or not 1<=seed<=30 or not team or team.lower() in {'team','teams'}: continue
   tk=key(team); sig=(tk,seed,conf)
   if sig in seen: continue
   try: wins=int(re.sub(r'[^0-9]','',vals[2])); losses=int(re.sub(r'[^0-9]','',vals[3]))
   except: wins=losses=None
   txt=' '.join(vals); q='PLAY-IN' if re.search(r'\bpi\b',txt,re.I) else ('PLAYOFFS' if re.search(r'\bp\b',txt,re.I) else '')
   rows.append({'season':season,'team':team,'team_key':tk,'seed':seed,'conference':conf,'wins':wins,'losses':losses,'postseason_qualification':q,'source':'Land of Basketball'}) ; seen.add(sig)
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
 for t in pd.read_html(io.StringIO(html)):
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
  tc=[i for i,c in enumerate(cols) if c=='team' or c.endswith('| team')]
  if len(tc)<2: continue
  for _,row in t.iterrows():
   lg=clean(row.iloc[li]).upper()
   if lg and lg!='NBA': continue
   m=re.search(r'(\d{4})',clean(row.iloc[yi]));
   if not m: continue
   w=clean(row.iloc[tc[0]]); l=clean(row.iloc[tc[1]])
   if not w or not l or w.lower()=='nan' or l.lower()=='nan': continue
   series.append({'year':int(m.group(1)),'league':'NBA','round':normalize_round(row.iloc[ri]),'winner':re.sub(r'\s*\(\d+\)\s*$','',w),'loser':re.sub(r'\s*\(\d+\)\s*$','',l)})
 out=[]; seen=set()
 for s in series:
  sig=(s['year'],s['round'],s['winner'],s['loser'])
  if sig not in seen: out.append(s); seen.add(sig)
 return out

def outcomes(series,year):
 by={}; ss=[s for s in series if s['year']==year and s.get('league','NBA')=='NBA']
 for s in ss:
  rr=ROUND_RANK.get(s['round'],0)
  for tm in (s['winner'],s['loser']):
   k=key(tm)
   if k and (k not in by or rr>by[k].get('_rank',0)): by[k]={'season_end_year':year,'team':tm,'team_key':k,'playoff_round':s['round'],'_rank':rr,'source':'Basketball-Reference'}
 for s in ss:
  if s['round']=='FINALS':
   wk,lk=key(s['winner']),key(s['loser'])
   if wk in by: by[wk].update(playoff_finish='CHAMPION',playoff_status='CHAMPION')
   if lk in by: by[lk].update(playoff_finish='MADE FINALS',playoff_status='MADE FINALS')
 for v in by.values(): v.setdefault('playoff_finish',v.get('playoff_round','UNKNOWN')); v.setdefault('playoff_status',v['playoff_finish']); v.pop('_rank',None)
 return by

def find_browser(explicit=None):
 if explicit and Path(explicit).exists(): return str(Path(explicit))
 names=['chrome','chrome.exe','msedge','msedge.exe','chromium','chromium.exe']
 candidates=[]
 for n in names:
  p=shutil.which(n)
  if p: candidates.append(p)
 for p in [os.environ.get('PROGRAMFILES','')+'\\Google\\Chrome\\Application\\chrome.exe',os.environ.get('PROGRAMFILES(X86)','')+'\\Google\\Chrome\\Application\\chrome.exe',os.environ.get('LOCALAPPDATA','')+'\\Google\\Chrome\\Application\\chrome.exe',os.environ.get('PROGRAMFILES','')+'\\Microsoft\\Edge\\Application\\msedge.exe',os.environ.get('PROGRAMFILES(X86)','')+'\\Microsoft\\Edge\\Application\\msedge.exe',os.environ.get('LOCALAPPDATA','')+'\\Microsoft\\Edge\\Application\\msedge.exe']:
  if p and Path(p).exists(): candidates.append(p)
 return candidates[0] if candidates else None

def is_block_page(html, host=''):
    h=(html or '').lower()
    return ('rate limited request' in h or '429 error' in h or 'error 429' in h or
            ('403 forbidden' in h and host in h) or 'access denied' in h[:5000])

def browser_fetch(browser,url,outfile,visible=False,wait=4):
    profile=Path(tempfile.mkdtemp(prefix='nba-per75-browser-'))
    cmd=[browser,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
         '--disable-background-networking','--disable-blink-features=AutomationControlled',
         f'--user-data-dir={profile}',f'--virtual-time-budget={max(wait,1)*1000}','--dump-dom',url]
    if visible: cmd=[x for x in cmd if x!='--headless=new']
    try:
        cp=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='ignore',timeout=max(wait+15,30))
        html=cp.stdout
        if len(html)<500: raise RuntimeError(f'browser returned only {len(html)} characters; stderr={cp.stderr[-500:]}')
        if is_block_page(html, 'sports-reference.com' if 'basketball-reference.com' in url else 'landofbasketball.com'):
            raise RuntimeError(f'source returned a rate-limit/access page ({len(html)} characters)')
        outfile.parent.mkdir(parents=True,exist_ok=True); outfile.write_text(html,encoding='utf-8'); return html
    finally:
        shutil.rmtree(profile,ignore_errors=True)

def interactive_cdp_fetch(browser,url,outfile,wait=5):
    """Open a visible browser with CDP. User can solve any interstitial, then press Enter."""
    import socket
    try:
        import websocket
    except Exception as e:
        raise RuntimeError('interactive browser fallback requires the Python websocket package') from e
    port=9222
    sock=socket.socket(); sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    try:
        sock.bind(('127.0.0.1',port)); sock.close()
    except OSError:
        sock.close(); port=0
        for _ in range(20):
            s=socket.socket(); s.bind(('127.0.0.1',0)); port=s.getsockname()[1]; s.close(); break
    profile=Path(tempfile.mkdtemp(prefix='nba-per75-interactive-'))
    cmd=[browser,f'--remote-debugging-port={port}','--no-first-run','--no-default-browser-check',
         '--disable-background-networking','--disable-blink-features=AutomationControlled',
         f'--user-data-dir={profile}',url]
    proc=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.time()+20; info=None
        while time.time()<deadline:
            try:
                info=json.loads(urllib.request.urlopen(f'http://127.0.0.1:{port}/json',timeout=1).read().decode())
                if info: break
            except Exception: time.sleep(.5)
        if not info: raise RuntimeError('could not connect to Chrome DevTools')
        page=next((x for x in info if x.get('type')=='page'),info[0])
        print('\nA browser window is open at the source URL.')
        print('If Basketball-Reference shows a rate-limit/interstitial page, resolve it in the browser.')
        print('When the actual page is loaded, return here and press ENTER.')
        input()
        ws=websocket.create_connection(page['webSocketDebuggerUrl'],timeout=10)
        msg_id=1
        ws.send(json.dumps({'id':msg_id,'method':'Runtime.evaluate','params':{'expression':'document.documentElement.outerHTML','returnByValue':True}}))
        html=None
        while True:
            data=json.loads(ws.recv())
            if data.get('id')==msg_id:
                html=data.get('result',{}).get('result',{}).get('value'); break
        ws.close()
        if not html or len(html)<500: raise RuntimeError('browser returned no usable DOM')
        if is_block_page(html, 'sports-reference.com' if 'basketball-reference.com' in url else 'landofbasketball.com'):
            raise RuntimeError('the page is still a rate-limit/access page after the interactive browser step')
        outfile.parent.mkdir(parents=True,exist_ok=True); outfile.write_text(html,encoding='utf-8'); return html
    finally:
        try: proc.terminate()
        except Exception: pass
        shutil.rmtree(profile,ignore_errors=True)

def main():
 ap=argparse.ArgumentParser(description='Build team competitive context using a real installed browser; no manual source bundles.')
 ap.add_argument('--browser'); ap.add_argument('--visible',action='store_true'); ap.add_argument('--wait',type=int,default=5); ap.add_argument('--start',type=int); ap.add_argument('--end',type=int); ap.add_argument('--refresh',action='store_true'); ap.add_argument('--interactive-fallback',action='store_true',help='open a visible browser and let you resolve a source block if headless acquisition is rate-limited'); args=ap.parse_args()
 browser=find_browser(args.browser)
 if not browser: raise SystemExit('ERROR: Could not find Chrome or Edge. Install/use Chrome or Edge, or pass --browser "C:\\path\\to\\chrome.exe".')
 print('[browser]',browser)
 df=pd.read_csv(MASTER,low_memory=False); seasons=sorted({str(x) for x in df['Season'].dropna()},key=lambda s:end_year(s) or 0)
 seasons=[s for s in seasons if end_year(s) and (args.start is None or end_year(s)>=args.start) and (args.end is None or end_year(s)<=args.end)]
 CACHE.mkdir(parents=True,exist_ok=True)
 bref_file=CACHE/'bref_series.html'
 if args.refresh or not bref_file.exists():
  print('[Basketball-Reference] fetching consolidated playoff series history in browser...')
  try: browser_fetch(browser,'https://www.basketball-reference.com/playoffs/series.html',bref_file,args.visible,args.wait)
  except Exception as e:
   print('  FAILED:',e)
   if args.interactive_fallback:
    try: interactive_cdp_fetch(browser,'https://www.basketball-reference.com/playoffs/series.html',bref_file,args.wait)
    except Exception as e2: print('  INTERACTIVE FAILED:',e2)
 if not bref_file.exists(): raise SystemExit('ERROR: Could not acquire Basketball-Reference series history. Re-run with --interactive-fallback if the site is rate-limiting the automated browser.')
 bref=parse_bref(bref_file.read_text(encoding='utf-8',errors='ignore'))
 result={'version':8,'sources':{'standings':'Land of Basketball browser-rendered year-by-year standings','playoffs':'Basketball-Reference browser-rendered playoffs/series.html','acquisition':'installed Chrome/Edge browser; source HTML cached locally'},'seasons':{}}
 failures=[]; land_rows=finish_rows=land_ok=0
 for i,season in enumerate(seasons,1):
  sy,ey=season_bounds(season); f=CACHE/f'land_{ey}.html'; url=f'https://www.landofbasketball.com/yearbyyear/{sy}_{ey}_standings.htm'
  print(f'[{i}/{len(seasons)}] [{season}] standings')
  if args.refresh or not f.exists():
   try: browser_fetch(browser,url,f,args.visible,args.wait)
   except Exception as e: print('  FAILED:',e); failures.append((season,'standings',str(e)))
  try: html=f.read_text(encoding='utf-8',errors='ignore') if f.exists() else '' ; standings=parse_land(html,season) if html else []
  except Exception as e: standings=[]; failures.append((season,'standings-parse',str(e)))
  if standings: land_ok+=1; land_rows+=len(standings)
  else: failures.append((season,'standings','missing or no rows'))
  print('  seeds parsed:',len(standings))
  outs=outcomes(bref,ey); finish_rows+=len(outs); print(f'  playoff teams parsed: {len(outs)}, series: {sum(1 for s in bref if s["year"]==ey)}')
  by={r['team_key']:dict(r) for r in standings}
  for k,r in outs.items(): by.setdefault(k,{}).update(r)
  for r in by.values():
   if 'playoff_finish' not in r:
    q=r.get('postseason_qualification'); r['playoff_finish']='PLAY-IN / MISSED PLAYOFFS' if q=='PLAY-IN' or r.get('seed') in (9,10) else 'MISSED PLAYOFFS'; r['playoff_status']=r['playoff_finish']
  result['seasons'][season]=list(by.values())
  if i<len(seasons): time.sleep(.5)
 meta={'seasons_requested':len(seasons),'standings_seasons_with_rows':land_ok,'standings_rows':land_rows,'playoff_finish_rows':finish_rows,'failures':failures,'browser':browser,'cached_source_dir':str(CACHE)}
 result['metadata']=meta; OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8'); REPORT.write_text(json.dumps(meta,indent=2),encoding='utf-8')
 print('\nBUILD COMPLETE'); print('SEASONS',len(seasons)); print('STANDINGS SEASONS',land_ok); print('SEED ROWS',land_rows); print('PLAYOFF FINISH ROWS',finish_rows); print('FAILURES',len(failures)); print('WROTE',OUT); print('WROTE',REPORT)
 if land_ok<len(seasons) or not finish_rows: return 2
 return 0
if __name__=='__main__': sys.exit(main())
