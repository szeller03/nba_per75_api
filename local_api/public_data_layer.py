"""Fast public query layer for NBA PER-75.

The public application should query this compact indexed SQLite layer instead of
opening the large research CSVs on each request. Source CSVs remain build-time
inputs and are not needed by these hot-path queries.
"""
from pathlib import Path
import os, sqlite3, json, re, threading, gzip, csv

ROOT=Path(os.environ.get("NBA_PER75_ROOT", str(Path(__file__).resolve().parents[1])))
DB=ROOT/'data'/'public'/'per75_public.sqlite3'
ELIGIBILITY=ROOT/'data'/'public'/'board_eligibility.sqlite3'
CAREER_SUPPORT=ROOT/'data'/'public'/'career_support.csv.gz'
_CONN_LOCAL=threading.local()
_CAREER_CACHE=None
_CAREER_LOCK=threading.Lock()
_WOWY_CACHE=None
_WOWY_LOCK=threading.Lock()
_TWO_P_CACHE={}
_TWO_P_LOCK=threading.Lock()
_PROFILE_BUNDLE_CACHE={}
_PROFILE_BUNDLE_LOCK=threading.Lock()

STAT_COLUMNS={
 'PTS_per75','FG_per75','FGA_per75','3P_per75','3PA_per75','2P_per75','2PA_per75',
 'FT_per75','FTA_per75','ORB_per75','DRB_per75','TRB_per75','AST_per75','STL_per75',
 'BLK_per75','TOV_per75','PF_per75','FG_pct','2P_pct','3P_pct','FT_pct','TS_pct',
 'FTr','3PAr','rTS','PER','BPM','OBPM','DBPM','VORP','WS/48','OWS','DWS','OREB_pct',
 'AST_pct','STL_pct','BLK_pct','TOV_pct','AST_TOV','DREB_pct','WOWY_Offense','WOWY_Defense','WOWY_Net'
}

def conn():
    # One read-only connection per HTTP worker thread. A single shared SQLite
    # connection was unsafe under concurrent public player-search requests.
    c=getattr(_CONN_LOCAL,'conn',None)
    if c is not None:
        return c
    if not DB.exists(): return None
    c=sqlite3.connect(f'file:{DB}?mode=ro&immutable=1',uri=True,check_same_thread=False)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    c.execute('PRAGMA cache_size=-65536')
    c.execute('PRAGMA temp_store=MEMORY')
    if ELIGIBILITY.exists():
        c.execute("ATTACH DATABASE ? AS elig", (str(ELIGIBILITY),))
    _CONN_LOCAL.conn=c
    return c

def norm(s): return re.sub(r'[^a-z0-9]+',' ',str(s or '').casefold()).strip()



def _percentile_from_values(values, higher=True):
    """Return 0-100 performance percentiles with average ranks for ties."""
    vals=[float(v) for v in values if v is not None]
    n=len(vals)
    if n<=1:
        return {vals[0]:100.0} if n==1 else {}
    out={}
    for v in set(vals):
        if higher:
            better=sum(x<v for x in vals)
        else:
            better=sum(x>v for x in vals)
        ties=sum(x==v for x in vals)
        out[v]=100.0*(better+0.5*(ties-1))/(n-1)
    return out

_LOWER_BETTER_SEASON_PCT_CACHE=None
_LOWER_BETTER_SEASON_PCT_LOCK=threading.Lock()

def _load_lower_better_season_percentiles(c):
    """Canonical regular-season percentiles for lower-is-better stats."""
    global _LOWER_BETTER_SEASON_PCT_CACHE
    if _LOWER_BETTER_SEASON_PCT_CACHE is not None:
        return _LOWER_BETTER_SEASON_PCT_CACHE
    with _LOWER_BETTER_SEASON_PCT_LOCK:
        if _LOWER_BETTER_SEASON_PCT_CACHE is not None:
            return _LOWER_BETTER_SEASON_PCT_CACHE
        out={}
        try:
            rows=c.execute("SELECT player_id,season,statistic,value FROM percentile WHERE statistic IN ('TOV_per75','TOV_pct') AND value IS NOT NULL").fetchall()
            grouped={}
            for r in rows:
                key=(str(r['statistic']),str(r['season']))
                grouped.setdefault(key,[]).append((str(r['player_id']),float(r['value'])))
            for key,items in grouped.items():
                pmap=_percentile_from_values([v for _,v in items],higher=False)
                for pid,v in items:
                    out[(key[0],key[1],pid)]=pmap.get(v)
        except Exception:
            out={}
        _LOWER_BETTER_SEASON_PCT_CACHE=out
        return out

def _career_stat_is_higher_better(stat):
    return str(stat) not in {"TOV_per75","TOV_pct","DRtg","Relative_DRtg"}

def _load_wowy_cache():
    """Load the canonical individual-season WOWY layer once for public bundles."""
    global _WOWY_CACHE
    if _WOWY_CACHE is not None:
        return _WOWY_CACHE
    with _WOWY_LOCK:
        if _WOWY_CACHE is not None:
            return _WOWY_CACHE
        # Prefer the canonical build-time cache, but also merge any site copy.
        # A stale/incomplete data/ copy must never mask newer cache rows.
        candidates=[ROOT/'local_api'/'cache'/'player_wowy_statistics_v1.csv',ROOT/'data'/'player_wowy_statistics_v1.csv']
        out={}
        for path in candidates:
            if not path.exists():
                continue
            try:
                with path.open('r',encoding='utf-8-sig',newline='') as f:
                    for row in csv.DictReader(f):
                        pid=str(row.get('Player_ID') or '').strip()
                        name=norm(row.get('Player') or '')
                        season=str(row.get('Season') or '').strip()
                        if not season:
                            continue
                        item={
                            'Player_ID':pid,'Player':row.get('Player'),'Season':season,
                            'SeasonEndYear':row.get('SeasonEndYear'),
                            'WOWY_Offense':_to_float(row.get('WOWY_Offense')),
                            'WOWY_Defense':_to_float(row.get('WOWY_Defense')),
                            'WOWY_Net':_to_float(row.get('WOWY_Net')),
                            'WOWY_Offense_Percentile':_to_float(row.get('WOWY_Offense_Percentile')),
                            'WOWY_Defense_Percentile':_to_float(row.get('WOWY_Defense_Percentile')),
                            'WOWY_Net_Percentile':_to_float(row.get('WOWY_Net_Percentile'))
                        }
                        out[(pid,season)]=item
                        out[(name,season)]=item
            except Exception:
                continue
        _WOWY_CACHE=out
        return out

def _to_float(value):
    try:
        if value in (None,'','null','None'): return None
        return float(value)
    except Exception:
        return None

def _payload_2p_pct(payload):
    """Derive historical 2P% from canonical raw or per-75 fields."""
    def num(k): return _to_float(payload.get(k))
    for a,b in (("2P_raw","2PA_raw"),("2P","2PA"),("2P_per75","2PA_per75"),("FG_raw","FGA_raw"),("FG_per75","FGA_per75")):
        x,y=num(a),num(b)
        if x is not None and y is not None and y>0:
            return x/y
    fga=num('FGA_raw')
    fg=num('FG_raw')
    if fg is not None and fga is not None and fga>0:
        return fg/fga
    return None

def _historical_2p_for_seasons(c, seasons):
    """Build/cache complete pre-1979 2P% populations from canonical season payloads."""
    wanted=[str(x) for x in seasons if str(x)[:4].isdigit() and int(str(x)[:4])<1979]
    missing=[x for x in wanted if x not in _TWO_P_CACHE]
    if missing:
        with _TWO_P_LOCK:
            missing=[x for x in wanted if x not in _TWO_P_CACHE]
            if missing:
                placeholders=','.join('?' for _ in missing)
                # Use the existing qualified FGA/75 population as the exact
                # single-season eligibility gate. This preserves the site's
                # established >=60% games and >=1,400 MP population without
                # inventing a second qualification rule for 2P%.
                eligible_by_season={}
                for season in missing:
                    erows=c.execute("SELECT player_id FROM percentile WHERE season=? AND statistic=? AND season_percentile IS NOT NULL",(season,'FGA_per75')).fetchall()
                    eligible_by_season[season]={str(r['player_id']).strip() for r in erows}
                rows=c.execute(f"SELECT player_id,season,payload FROM seasons WHERE season_type=? AND season IN ({placeholders})",('Regular Season',*missing)).fetchall()
                buckets={x:[] for x in missing}
                for r in rows:
                    if eligible_by_season.get(str(r['season']),set()) and str(r['player_id']).strip() not in eligible_by_season[str(r['season'])]:
                        continue
                    try: payload=json.loads(r['payload']); value=_payload_2p_pct(payload)
                    except Exception: value=None; payload={}
                    if value is not None:
                        buckets.setdefault(str(r['season']),[]).append((str(r['player_id']),payload.get('Player') or payload.get('Player_Name'),value))
                for season in missing:
                    vals=[x[2] for x in buckets.get(season,[])]
                    pct=_percentile_from_values(vals,higher=True)
                    by_key={}
                    for pid,name,value in buckets.get(season,[]):
                        item={'player_id':pid,'player_name':name,'value':value,'season_percentile':pct.get(value)}
                        by_key[pid]=item
                        by_key[norm(name)]=item
                    _TWO_P_CACHE[season]=by_key
    return _TWO_P_CACHE

def era_for(season):
    m=re.match(r'^(\d{4})',str(season or ''))
    if not m:return ''
    y=int(m.group(1))
    if 1952<=y<=1969:return '1952-1969'
    if 1970<=y<=1979:return '1970-1979'
    if 1980<=y<=1990:return '1980-1990'
    if 1991<=y<=1998:return '1991-1998'
    if 1999<=y<=2006:return '1999-2006'
    if 2007<=y<=2013:return '2007-2013'
    if 2014<=y<=2020:return '2014-2020'
    if 2021<=y<=2026:return '2021-2026'
    return ''

def era_bounds(era):
    return {
        '1952-1969':(1952,1969),'1970-1979':(1970,1979),'1980-1990':(1980,1990),
        '1991-1998':(1991,1998),'1999-2006':(1999,2006),'2007-2013':(2007,2013),
        '2014-2020':(2014,2020),'2021-2026':(2021,2026)
    }.get(str(era or '').strip())

def search_players_batch(names):
    """Resolve a finite list of exact curated player names in one API call.

    This is intentionally separate from free-text search. It removes the
    frontend's N-request startup pattern without changing search semantics.
    """
    c=conn()
    if c is None:return {}
    names=[str(x).strip() for x in (names or []) if str(x).strip()]
    if not names:return {}
    out={}
    sql='SELECT player_id,player_name,display_name,slug,nba_player_id,headshot_url,headshot_source,headshot_status,qualified_profile,qualified_seasons\n                    FROM players\n                    WHERE lower(player_name)=lower(?)\n                    ORDER BY qualified_profile DESC, qualified_seasons DESC, player_name\n                    LIMIT 1'
    for name in names:
        try:
            r=c.execute(sql,(name,)).fetchone()
            if r:
                out[name]=dict(r)
        except Exception:
            continue
    return out

def search_players(q='',limit=50):
    c=conn()
    if c is None:return []
    q=str(q or '').strip()
    if q:
        terms=[x for x in norm(q).split() if x]
        if terms:
            # AND across search terms, using one indexed-ish compact search field.
            where=' AND '.join(['search_key LIKE ?']*len(terms)); params=[f'%{x}%' for x in terms]
            rows=c.execute(f'SELECT player_id,player_name,display_name,slug,nba_player_id,headshot_url,headshot_source,headshot_status,qualified_profile,qualified_seasons FROM players WHERE {where} ORDER BY player_name LIMIT ?',(*params,int(limit))).fetchall()
        else: rows=[]
    else:
        rows=c.execute('SELECT player_id,player_name,display_name,slug,nba_player_id,headshot_url,headshot_source,headshot_status,qualified_profile,qualified_seasons FROM players ORDER BY player_name LIMIT ?', (int(limit),)).fetchall()
    out=[]; seen=set()
    for r in rows:
        d=dict(r); key=norm(d.get('player_name','')).replace('*','')
        if key in seen: continue
        seen.add(key); out.append(d)
        if len(out)>=int(limit): break
    return out

def _player_row(c,pid):
    r=c.execute('SELECT player_id,player_name,display_name,slug,nba_player_id,headshot_url,headshot_source,headshot_status,qualified_profile,qualified_seasons FROM players WHERE player_id=?',(str(pid),)).fetchone()
    return dict(r) if r else None

def _percentiles(c,pid,season):
    rows=[dict(r) for r in c.execute('SELECT statistic,value,season_percentile,era_percentile,historical_percentile,player_name,season,season_end_year,era FROM percentile WHERE player_id=? AND season=?',(str(pid),str(season))).fetchall()]
    _lb=_load_lower_better_season_percentiles(c)
    for _r in rows:
        _st=str(_r.get('statistic') or '')
        if _st in {'TOV_per75','TOV_pct'}:
            _pc=_lb.get((_st,str(season),str(pid)))
            if _pc is not None: _r['season_percentile']=_pc
    # Historical 2P% is derivable from the canonical season payload even when
    # the legacy percentile table predates that field. This specifically covers
    # the pre-three-point era instead of borrowing an unrelated FGA percentile.
    if str(season)[:4].isdigit() and int(str(season)[:4])<1979 and not any(r.get('statistic')=='2P_pct' for r in rows):
        pop=_historical_2p_for_seasons(c,[season]).get(str(season),{})
        hit=pop.get(str(pid))
        if hit is None:
            hit=pop.get(norm(next((r.get('player_name') for r in rows if r.get('player_name')),'')))
        if hit:
            rows.append({'statistic':'2P_pct','value':hit.get('value'),'season_percentile':hit.get('season_percentile'),'era_percentile':None,'historical_percentile':None,'player_name':hit.get('player_name'),'season':season,'season_end_year':str(season)[-2:],'era':era_for(season)})
    if str(season)[:4].isdigit() and int(str(season)[:4])<1979 and not any(r.get('statistic')=='2PA_per75' for r in rows):
        f=next((r for r in rows if r.get('statistic')=='FGA_per75'),None)
        if f:
            rows.append({'statistic':'2PA_per75','value':f.get('value'),'season_percentile':f.get('season_percentile'),'era_percentile':f.get('era_percentile'),'historical_percentile':f.get('historical_percentile'),'player_name':f.get('player_name'),'season':f.get('season'),'season_end_year':f.get('season_end_year'),'era':f.get('era')})
    return rows

def _bundle(c,pid,season,season_type, pct_rows=None, player=None):
    r=c.execute('SELECT payload FROM seasons WHERE player_id=? AND season=? AND season_type=?',(str(pid),str(season),str(season_type))).fetchone()
    if not r:return None
    p=json.loads(r['payload'])
    pct=list(pct_rows.get(str(season), [])) if pct_rows is not None else (_percentiles(c,pid,season) if season_type=='Regular Season' else [])
    vals={k:v for k,v in p.items() if k not in {'Player_ID','Player','Season','SeasonEndYear','Season_Type','Team','Pos','Age'}}
    if season_type=='Regular Season':
        w=_load_wowy_cache()
        wr=w.get((str(pid).strip(),str(season)))
        if wr is None:
            pname=p.get('Player') or p.get('Player_Name')
            wr=w.get((norm(pname),str(season)))
        if wr:
            for _st in ('WOWY_Offense','WOWY_Defense','WOWY_Net'):
                if wr.get(_st) is not None:
                    vals[_st]=wr.get(_st)
                pct_key=_st+'_Percentile'
                if wr.get(pct_key) is not None:
                    pct=[x for x in pct if x.get('statistic')!=_st]
                    pct.append({'statistic':_st,'value':wr.get(_st),'season_percentile':wr.get(pct_key),'era_percentile':None,'historical_percentile':None,'player_name':wr.get('Player'),'season':wr.get('Season'),'season_end_year':wr.get('SeasonEndYear'),'era':era_for(season)})
    # Hydrate 2P% from canonical underlying makes/attempts whenever the compact
    # payload omitted the derived field. This applies to every season, not just
    # the pre-three-point era; the historical cases are simply the most common.
    if season_type=='Regular Season' and vals.get('2P_pct') is None:
        two_pct=_payload_2p_pct(p)
        if two_pct is not None:
            vals['2P_pct']=two_pct

    if season_type=='Regular Season' and str(season)[:4].isdigit() and int(str(season)[:4])<1979 and vals.get('FGA_per75') is not None:
        vals['2PA_per75']=vals['FGA_per75']
        f=next((z for z in pct if z.get('statistic')=='FGA_per75'),None)
        if f:
            found=False
            for x in pct:
                if x.get('statistic')=='2PA_per75':
                    x.update({'value':f.get('value'),'season_percentile':f.get('season_percentile'),'era_percentile':f.get('era_percentile'),'historical_percentile':f.get('historical_percentile')}); found=True; break
            if not found:
                pct.append({'statistic':'2PA_per75','value':f.get('value'),'season_percentile':f.get('season_percentile'),'era_percentile':f.get('era_percentile'),'historical_percentile':f.get('historical_percentile'),'player_name':f.get('player_name'),'season':f.get('season'),'season_end_year':f.get('season_end_year'),'era':f.get('era')})
    player=player or _player_row(c,pid) or {}
    profile=dict(p)
    return {'found':True,'view':'season','is_career':False,'player':{'player_id':str(pid),'player_name':p.get('Player') or p.get('Player_Name'),'headshot_url':player.get('headshot_url','')},'seasons':[season],
            'individual_seasons':[season],'profile':profile,'statistic_values':vals,
            'statistic_values_normalized':vals,'percentiles':pct,'playoff_available':False,
            'playoff_source':'public_data_layer','playoff_statistics':{},'season_type':season_type,
            'career_note':'Season payload served from the indexed public data layer.'}

def warm_public_profile_data():
    """Warm the expensive one-time public profile enrichments at API startup.

    The indexed SQLite query itself is fast, but the first profile bundle can
    otherwise pay for loading the WOWY CSV, the career-support gzip, and the
    historical pre-1979 2P% population. Those are shared caches, so paying that
    cost once during the API warm-up keeps the user's first profile request on
    the fast path without changing the returned data.
    """
    c=conn()
    if c is None:
        return False
    _career_support()
    _load_wowy_cache()
    try:
        seasons=[r[0] for r in c.execute("SELECT DISTINCT season FROM seasons WHERE season_type=?",('Regular Season',)).fetchall()]
        _historical_2p_for_seasons(c,seasons)
    except Exception:
        # Historical 2P% is an enrichment; failure must not prevent the core
        # public profile layer from serving.
        pass
    return True


def player_season_bundles(pid,season_type='Regular Season'):
    cache_key=(str(pid).strip(),str(season_type))
    cached=_PROFILE_BUNDLE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    c=conn()
    if c is None:return {'found':False,'seasons':[],'rows':[]}
    player=_player_row(c,pid)
    if not player:return {'found':False,'seasons':[],'rows':[]}
    season_rows=c.execute('SELECT season,season_end_year,payload FROM seasons WHERE player_id=? AND season_type=? ORDER BY season_end_year',(str(pid),str(season_type))).fetchall()
    seasons=[r['season'] for r in season_rows]
    # Batch the percentile lookup once for the whole profile. The previous
    # implementation executed one percentile query per season, which made
    # long-career profiles take many seconds despite the compact SQLite layer.
    pct_by_season={}
    if season_type=='Regular Season' and seasons:
        placeholders=','.join('?' for _ in seasons)
        rows=c.execute(f'SELECT statistic,value,season_percentile,era_percentile,historical_percentile,player_name,season,season_end_year,era FROM percentile WHERE player_id=? AND season IN ({placeholders})',(str(pid),*seasons)).fetchall()
        for r in rows:
            d=dict(r); pct_by_season.setdefault(str(d.get('season')),[]).append(d)
        _lb=_load_lower_better_season_percentiles(c)
        for _s,_rows in pct_by_season.items():
            for _r in _rows:
                _st=str(_r.get('statistic') or '')
                if _st in {'TOV_per75','TOV_pct'}:
                    _pc=_lb.get((_st,str(_s),str(pid)))
                    if _pc is not None: _r['season_percentile']=_pc
        # Add canonical historical 2P% and individual-season WOWY to the same
        # batched profile payload. These are cached so long profiles remain fast.
        hist2p=_historical_2p_for_seasons(c,[x for x in seasons if str(x)[:4].isdigit() and int(str(x)[:4])<1979])
        wowy=_load_wowy_cache()
        for s in seasons:
            if str(s)[:4].isdigit() and int(str(s)[:4])<1979:
                hit=hist2p.get(str(s),{}).get(str(pid))
                if hit and not any(x.get('statistic')=='2P_pct' for x in pct_by_season.get(str(s),[])):
                    pct_by_season.setdefault(str(s),[]).append({'statistic':'2P_pct','value':hit.get('value'),'season_percentile':hit.get('season_percentile'),'era_percentile':None,'historical_percentile':None,'player_name':hit.get('player_name'),'season':str(s),'season_end_year':str(s)[-2:],'era':era_for(s)})
            wr=wowy.get((str(pid).strip(),str(s)))
            if wr is None:
                wr=wowy.get((norm(player.get('player_name') or player.get('display_name') or ''),str(s)))
            if wr:
                for _st in ('WOWY_Offense','WOWY_Defense','WOWY_Net'):
                    pct_by_season.setdefault(str(s),[])
                    if wr.get(_st) is not None:
                        # Value is also added below to statistic_values.
                        if not any(x.get('statistic')==_st for x in pct_by_season[str(s)]):
                            pct_by_season[str(s)].append({'statistic':_st,'value':wr.get(_st),'season_percentile':wr.get(_st+'_Percentile'),'era_percentile':None,'historical_percentile':None,'player_name':wr.get('Player'),'season':wr.get('Season'),'season_end_year':wr.get('SeasonEndYear'),'era':era_for(s)})
            
        for s in seasons:
            if str(s)[:4].isdigit() and int(str(s)[:4])<1979 and not any(x.get('statistic')=='2PA_per75' for x in pct_by_season.get(str(s),[])):
                f=next((x for x in pct_by_season.get(str(s),[]) if x.get('statistic')=='FGA_per75'),None)
                if f:
                    pct_by_season.setdefault(str(s),[]).append({'statistic':'2PA_per75','value':f.get('value'),'season_percentile':f.get('season_percentile'),'era_percentile':f.get('era_percentile'),'historical_percentile':f.get('historical_percentile'),'player_name':f.get('player_name'),'season':f.get('season'),'season_end_year':f.get('season_end_year'),'era':f.get('era')})
    bundles=[]
    for row in season_rows:
        s=row['season']
        p=json.loads(row['payload'])
        pct=pct_by_season.get(str(s),[])
        vals={k:v for k,v in p.items() if k not in {'Player_ID','Player','Season','SeasonEndYear','Season_Type','Team','Pos','Age'}}
        if season_type=='Regular Season':
            for _wstat in ('WOWY_Offense','WOWY_Defense','WOWY_Net'):
                _wr=next((x for x in pct if x.get('statistic')==_wstat),None)
                if _wr and _wr.get('value') is not None:
                    vals[_wstat]=_wr.get('value')
            if vals.get('2P_pct') is None:
                _two_pct=_payload_2p_pct(p)
                if _two_pct is not None:
                    vals['2P_pct']=_two_pct
        if season_type=='Regular Season' and str(s)[:4].isdigit() and int(str(s)[:4])<1979 and vals.get('FGA_per75') is not None:
            vals['2PA_per75']=vals['FGA_per75']
            f=next((x for x in pct if x.get('statistic')=='FGA_per75'),None)
            if f:
                for x in pct:
                    if x.get('statistic')=='2PA_per75':
                        x.update({'value':f.get('value'),'season_percentile':f.get('season_percentile'),'era_percentile':f.get('era_percentile'),'historical_percentile':f.get('historical_percentile')})
                        break
        b={'found':True,'view':'season','is_career':False,'player':{'player_id':str(pid),'player_name':p.get('Player') or p.get('Player_Name'),'headshot_url':player.get('headshot_url','')},'seasons':[s],
           'individual_seasons':[s],'profile':p,'statistic_values':vals,'statistic_values_normalized':vals,'percentiles':pct,'playoff_available':False,
           'playoff_source':'public_data_layer','playoff_statistics':{},'season_type':season_type,'career_note':'Season payload served from the indexed public data layer.'}
        bundles.append({'season':s,'bundle':b})
    career_payload=_career_support().get(str(pid)) if str(season_type)=='Regular Season' else None
    if career_payload:
        vals=career_payload['values']; plist=[{'Statistic':k,'Career_Value':v,'Career_Percentile':career_payload['percentiles'].get(k),'Career_Percentile_Qualified':career_payload['percentiles'].get(k) is not None} for k,v in vals.items()]
        profile=dict(vals); profile.update({'Player':career_payload['player_name'],'G':career_payload['G'],'MP':career_payload['MP'],'League':'NBA','Player_ID':str(pid),'Season':'Career','Qualified_Career':career_payload['Qualified_Career']})
        cb={'found':True,'view':'Career','is_career':True,'player':{'player_id':str(pid),'player_name':career_payload['player_name'],'headshot_url':player.get('headshot_url','')},'seasons':[],'individual_seasons':[],'profile':profile,'statistic_values':vals,'statistic_values_normalized':vals,'percentiles':plist,'playoff_available':False,'playoff_statistics':{},'season_type':'Regular Season','career_note':'Career aggregate served from indexed public performance layer.'}
    else:
        cb=None
    result={'found':True,'player':player,'seasons':seasons,'rows':bundles,'career':cb,'season_type':season_type}
    with _PROFILE_BUNDLE_LOCK:
        _PROFILE_BUNDLE_CACHE[cache_key]=result
    return result

def player_season_bundle(pid,season,season_type='Regular Season'):
    c=conn()
    if c is None:return {'found':False}
    player=_player_row(c,pid)
    if not player:return {'found':False}
    b=_bundle(c,pid,season,season_type)
    return b or {'found':False}



def _career_support():
    global _CAREER_CACHE
    if _CAREER_CACHE is not None:
        return _CAREER_CACHE
    out={}
    if not CAREER_SUPPORT.exists():
        _CAREER_CACHE=out; return out
    with gzip.open(CAREER_SUPPORT,'rt',encoding='utf-8',newline='') as f:
        for row in csv.DictReader(f):
            pid=row.get('player_id','')
            if not pid: continue
            vals={}; pcts=[]
            for k,v in row.items():
                if k.startswith('v__') and v not in ('',None):
                    try: vals[k[3:]]=float(v)
                    except: vals[k[3:]]=v
                elif k.startswith('p__') and v not in ('',None):
                    try: pcts[k[3:]]=float(v)
                    except: pass
            out[pid]={'player_name':row.get('player_name',''),'G':float(row['G']) if row.get('G') else None,'MP':float(row['MP']) if row.get('MP') else None,'Qualified_Career':row.get('Qualified_Career') in ('1','True','true'),'values':vals,'percentiles':{}}
    # Recompute Career percentiles from the authoritative career values rather
    # than trusting legacy p__ columns, which used an inconsistent rank scale.
    qualified=[r for r in out.values() if r.get('Qualified_Career')]
    stats=sorted({k for r in qualified for k in r.get('values',{})})
    for stat in stats:
        raw=[r.get('values',{}).get(stat) for r in qualified]
        clean=[float(v) for v in raw if v is not None]
        pmap=_percentile_from_values(clean,higher=_career_stat_is_higher_better(stat))
        for r in qualified:
            v=r.get('values',{}).get(stat)
            if v is not None:
                r.setdefault('percentiles',{})[stat]=pmap.get(float(v))
    _CAREER_CACHE=out
    return out

def big_board(statistic='PTS_per75',season='Historical Percentile',context='Historical',sort='desc',search='',limit=100,era=''):
    c=conn()
    if c is None:return {'rows':[],'count':0,'ready':False}
    stat=str(statistic or 'PTS_per75')
    if stat not in STAT_COLUMNS:return {'rows':[],'count':0,'error':'Unsupported statistic'}
    source_stat=stat
    if stat=='2PA_per75' and season and season!='Historical Percentile' and str(season)[:4].isdigit() and int(str(season)[:4])<1979:
        source_stat='FGA_per75'
    pct={'Season':'season_percentile','Era':'era_percentile','Historical':'historical_percentile'}.get(str(context),'historical_percentile')
    params=[]; where=['statistic=?']; params.append(source_stat)
    if season and season!='Historical Percentile': where.append('season=?'); params.append(str(season))
    if era:
        bounds=era_bounds(era)
        if bounds:
            where.append('season_end_year BETWEEN ? AND ?'); params.extend(bounds)
        else:
            where.append('era=?'); params.append(str(era))
    if search:
        where.append('player_name LIKE ?'); params.append('%'+str(search).casefold()+'%')
    order='ASC' if str(sort).casefold()=='asc' else 'DESC'
    # Preserve the legacy Big Board's qualification gates. The public layer
    # is only a transport optimization; it must rank the same eligible
    # population as the canonical API. Qualification is precomputed at build
    # time in a tiny sidecar SQLite database so this remains a fast indexed join.
    stat_key=stat
    if stat_key in {'FG_pct','FT_pct','3P_pct','TS_pct'}:
        elig_col={'FG_pct':'fg_pct','FT_pct':'ft_pct','3P_pct':'threep_pct','TS_pct':'ts_pct'}[stat_key]
    elif stat_key in {'PER','ORB_pct','DRB_pct','TRB_pct','AST_pct','STL_pct','BLK_pct','TOV_pct','WS/48','WS_48','DRtg'} or stat_key in {'rTS','Relative_TS','Relative_TS%'}:
        elig_col='advanced'
    else:
        elig_col='basic'
    join = f"JOIN elig.eligibility e ON e.player_id=p.player_id AND e.season=p.season AND e.{elig_col}=1"
    sql=f'''SELECT p.player_id,p.player_name,p.season,p.season_end_year,p.value,p.{pct} AS percentile,p.era FROM percentile p {join} WHERE {' AND '.join(where).replace('statistic=?','p.statistic=?').replace('season=?','p.season=?').replace('era=?','p.era=?').replace('player_name LIKE ?','p.player_name LIKE ?')} ORDER BY p.{pct} {order} LIMIT ?'''
    rows=[dict(r) for r in c.execute(sql,(*params,int(limit))).fetchall()]
    out=[]
    for i,r in enumerate(rows,1):
        out.append({'rank':i,'player_id':r['player_id'],'player_name':r['player_name'],'season':r['season'],'season_label':r['season'],'value':r['value'],'percentile':r['percentile']})
    return {'rows':out,'count':len(out),'total':len(out),'season':season or 'Historical Percentile','historical_scope':str(context)=='Historical','career_scope':False,'context':context,'statistic':stat,'season_type':'Regular Season','public_layer':True}


def big_board_companion(statistic='PTS_per75', season='Historical Percentile', context='Historical', player_ids=None, era=''):
    """Return companion data only for player IDs already shown by the primary board."""
    c=conn()
    if c is None: return {'rows':[], 'count':0, 'ready':False}
    stat=str(statistic or 'PTS_per75')
    if stat not in STAT_COLUMNS: return {'rows':[], 'count':0, 'error':'Unsupported statistic'}
    ids=[]
    for x in (player_ids or []):
        x=str(x or '').strip()
        if x and x not in ids: ids.append(x)
    ids=ids[:500]
    if not ids: return {'rows':[], 'count':0, 'public_layer':True, 'companion':True}
    source_stat=stat
    if stat=='2PA_per75' and season and season!='Historical Percentile' and str(season)[:4].isdigit() and int(str(season)[:4])<1979:
        source_stat='FGA_per75'
    pct={'Season':'season_percentile','Era':'era_percentile','Historical':'historical_percentile'}.get(str(context),'historical_percentile')
    where=['p.statistic=?']; params=[source_stat]
    if season and season!='Historical Percentile': where.append('p.season=?'); params.append(str(season))
    if era:
        bounds=era_bounds(era)
        if bounds:
            where.append('p.season_end_year BETWEEN ? AND ?'); params.extend(bounds)
        else:
            where.append('p.era=?'); params.append(str(era))
    ph=','.join('?' for _ in ids)
    where.append(f'p.player_id IN ({ph})'); params.extend(ids)
    sql='SELECT p.player_id,p.player_name,p.season,p.season_end_year,p.value,p.'+pct+' AS percentile,p.era FROM percentile p WHERE '+' AND '.join(where)
    rows=[dict(r) for r in c.execute(sql,params).fetchall()]
    return {'rows':[{'player_id':r['player_id'],'player_name':r['player_name'],'season':r['season'],'season_label':r['season'],'value':r['value'],'percentile':r['percentile']} for r in rows], 'count':len(rows), 'total':len(rows), 'season':season or 'Historical Percentile', 'historical_scope':str(context)=='Historical', 'career_scope':False, 'context':context, 'statistic':stat, 'season_type':'Regular Season', 'public_layer':True, 'companion':True}


def explorer_population(x_statistic='PTS_per75', y_statistic='rTS', season='Historical Percentile', season_type='Regular Season', era='', search='', x_min=None, x_max=None, y_min=None, y_max=None, limit=100, scope='single'):
    """Explorer population: X is the dominant ranking variable; Y describes it."""
    c=conn()
    if c is None: return {'rows':[], 'count':0, 'total':0, 'ready':False}
    xs=str(x_statistic or 'PTS_per75'); ys=str(y_statistic or 'rTS')
    if xs not in STAT_COLUMNS or ys not in STAT_COLUMNS: return {'rows':[], 'count':0, 'total':0, 'error':'Unsupported Explorer statistic'}
    if str(season_type).casefold() not in {'regular season','regular',''} or str(scope).casefold() != 'single': return {'rows':[], 'count':0, 'total':0, 'ready':False, 'fallback':True}
    def source_stat(stat):
        if stat=='2PA_per75' and season and season!='Historical Percentile' and str(season)[:4].isdigit() and int(str(season)[:4])<1979: return 'FGA_per75'
        return stat
    xsrc, ysrc = source_stat(xs), source_stat(ys)
    # WOWY values live in the canonical WOWY cache rather than the compact
    # percentile table. Explorer must still expose them as first-class X/Y
    # variables without changing any underlying profile/Big Board data.
    wowy_stats={"WOWY_Offense","WOWY_Defense","WOWY_Net"}
    if xs in wowy_stats or ys in wowy_stats:
        wowy=_load_wowy_cache()
        def _elig_col_local(stat):
            if stat in {'FG_pct','FT_pct','3P_pct','TS_pct'}: return {'FG_pct':'fg_pct','FT_pct':'ft_pct','3P_pct':'threep_pct','TS_pct':'ts_pct'}[stat]
            if stat in {'PER','ORB_pct','DRB_pct','AST_pct','STL_pct','BLK_pct','TOV_pct','WS/48','WS_48','DRtg','rTS','Relative_TS','Relative_TS%'}: return 'advanced'
            return 'basic'
        # Load the selected non-WOWY statistic(s) into PID/season maps, while
        # retaining the same qualification gates used by ordinary Explorer.
        value_maps={}
        for stat in {xs,ys}:
            if stat in wowy_stats: continue
            src=source_stat(stat); ecol=_elig_col_local(stat)
            sql=f"SELECT p.player_id,p.player_name,p.season,p.season_end_year,p.era,p.value FROM percentile p JOIN elig.eligibility e ON e.player_id=p.player_id AND e.season=p.season AND e.{ecol}=1 WHERE p.statistic=?"
            rows_sql=[dict(r) for r in c.execute(sql,(src,)).fetchall()]
            # Keep both canonical ID and normalized-name keys. The WOWY cache is
            # historically keyed by stable player slugs, while the compact public
            # percentile DB can contain a different player-id namespace.
            vm={}
            for r in rows_sql:
                pid=str(r.get('player_id') or '').strip()
                season_key=str(r.get('season') or '').strip()
                name_key=norm(r.get('player_name') or '')
                if season_key and pid:
                    vm[(pid,season_key)]=r
                if season_key and name_key:
                    vm[(name_key,season_key)]=r
            value_maps[stat]=vm
        # When both axes are WOWY, use the normal PTS/75 qualified layer only
        # as the observation/season anchor. This keeps population behavior stable.
        anchor_map={}
        if xs in wowy_stats and ys in wowy_stats:
            anchor_sql="SELECT p.player_id,p.player_name,p.season,p.season_end_year,p.era,p.value FROM percentile p JOIN elig.eligibility e ON e.player_id=p.player_id AND e.season=p.season AND e.basic=1 WHERE p.statistic=?"
            anchor_map={}
            for r0 in c.execute(anchor_sql,('PTS_per75',)).fetchall():
                r=dict(r0); pid0=str(r.get('player_id') or '').strip(); season0=str(r.get('season') or '').strip(); name0=norm(r.get('player_name') or '')
                if pid0 and season0: anchor_map[(pid0,season0)]=r
                if name0 and season0: anchor_map[(name0,season0)]=r
        out=[]
        seen=set()
        for key,wr in wowy.items():
            if not isinstance(key,tuple) or len(key)!=2: continue
            pid=str(wr.get('Player_ID') or '').strip(); s=str(wr.get('Season') or '').strip()
            # Process only canonical ID-keyed rows; name-keyed aliases are
            # intentionally ignored to prevent duplicate observations.
            if key != (pid,s) or not pid or not s or (pid,s) in seen: continue
            seen.add((pid,s))
            name_key=norm(wr.get('Player') or '')
            wkey=(pid,s)
            nkey=(name_key,s)
            if xs in wowy_stats:
                xv=wr.get(xs)
                base=(anchor_map.get(wkey) or anchor_map.get(nkey)) if xs in wowy_stats and ys in wowy_stats else (value_maps.get(ys,{}).get(wkey) or value_maps.get(ys,{}).get(nkey))
            else:
                base=value_maps.get(xs,{}).get(wkey) or value_maps.get(xs,{}).get(nkey); xv=base.get('value') if base else None
            if ys in wowy_stats: yv=wr.get(ys)
            else:
                ybase=value_maps.get(ys,{}).get(wkey) or value_maps.get(ys,{}).get(nkey); yv=ybase.get('value') if ybase else None
            if xs in wowy_stats and ys not in wowy_stats and base is None: continue
            if ys in wowy_stats and xs not in wowy_stats and base is None: continue
            if xs in wowy_stats and ys in wowy_stats and not (anchor_map.get(wkey) or anchor_map.get(nkey)): continue
            if xv is None or yv is None: continue
            try: xv=float(xv); yv=float(yv)
            except Exception: continue
            pname=wr.get('Player') or (base or {}).get('player_name') or ''
            anchor=(anchor_map.get(wkey) or anchor_map.get(nkey) or {})
            season_era=(base or {}).get('era') or anchor.get('era') or ''
            if season and season not in {'Historical Percentile','Historical','All','all','All Seasons'} and s!=str(season): continue
            if era and str(season_era)!=str(era): continue
            if search and str(pname).casefold().find(str(search).casefold())<0: continue
            if x_min is not None and xv<float(x_min) or x_max is not None and xv>float(x_max) or y_min is not None and yv<float(y_min) or y_max is not None and yv>float(y_max): continue
            out.append({'player_id':pid,'player_name':pname,'season':s,'season_end_year':(base or {}).get('season_end_year') or anchor_map.get((pid,s),{}).get('season_end_year') or wr.get('SeasonEndYear'),'x_value':xv,'y_value':yv})
        raw=sorted(out,key=lambda r:(-r['x_value'],str(r['player_name'] or '').casefold()))
        cap=max(1,min(int(limit or 100),100)); total=len(raw)
        rows=[{'rank':i,'player_id':r['player_id'],'player_name':r['player_name'],'season':r['season'],'season_label':r['season'],'xValue':r['x_value'],'yValue':r['y_value'],'x_percentile':None,'y_percentile':None,'headshot_url':None} for i,r in enumerate(raw[:cap],1)]
        season_rows=sorted({r['season'] for r in raw},key=lambda z:int(str(z)[:4]) if str(z)[:4].isdigit() else 0)
        return {'rows':rows,'count':len(rows),'total':total,'population_total':total,'available_bounds':{'xmin':min((r['xValue'] for r in rows),default=None),'xmax':max((r['xValue'] for r in rows),default=None),'ymin':min((r['yValue'] for r in rows),default=None),'ymax':max((r['yValue'] for r in rows),default=None)},'x_statistic':xs,'y_statistic':ys,'season':season or 'Historical Percentile','season_type':'Regular Season','scope':'single','era':era or '','ranked_by':'x','season_options':[{'value':s,'label':s} for s in season_rows],'rank_direction':'desc','public_layer':True}
    def elig_col(stat):
        if stat in {'FG_pct','FT_pct','3P_pct','TS_pct'}: return {'FG_pct':'fg_pct','FT_pct':'ft_pct','3P_pct':'threep_pct','TS_pct':'ts_pct'}[stat]
        if stat in {'PER','ORB_pct','DRB_pct','AST_pct','STL_pct','BLK_pct','TOV_pct','WS/48','WS_48','DRtg','rTS','Relative_TS','Relative_TS%'}: return 'advanced'
        return 'basic'
    ex, ey = elig_col(xs), elig_col(ys)
    conditions=[]; params=[]
    if season and season not in {'Historical Percentile','Historical','All','all','All Seasons'}: conditions.append('x.season=?'); params.append(str(season))
    if era and era not in {'All','all'}: conditions.append('x.era=?'); params.append(str(era))
    if search: conditions.append('x.player_name LIKE ?'); params.append('%'+str(search)+'%')
    if x_min is not None: conditions.append('CAST(x.value AS REAL)>=?'); params.append(float(x_min))
    if x_max is not None: conditions.append('CAST(x.value AS REAL)<=?'); params.append(float(x_max))
    if y_min is not None: conditions.append('CAST(y.value AS REAL)>=?'); params.append(float(y_min))
    if y_max is not None: conditions.append('CAST(y.value AS REAL)<=?'); params.append(float(y_max))
    conditions += ['x.value IS NOT NULL','y.value IS NOT NULL']
    sql=f"""SELECT x.player_id,x.player_name,x.season,x.season_end_year,x.value AS x_value,y.value AS y_value,x.season_percentile AS x_percentile,y.season_percentile AS y_percentile
            FROM percentile x JOIN percentile y ON y.player_id=x.player_id AND y.season=x.season
            JOIN elig.eligibility ex ON ex.player_id=x.player_id AND ex.season=x.season AND ex.{ex}=1
            JOIN elig.eligibility ey ON ey.player_id=y.player_id AND ey.season=y.season AND ey.{ey}=1
            WHERE x.statistic=? AND y.statistic=? AND {' AND '.join(conditions)}
            ORDER BY CAST(x.value AS REAL) DESC, x.player_name COLLATE NOCASE ASC"""
    try: raw=[dict(r) for r in c.execute(sql,(xsrc,ysrc,*params)).fetchall()]
    except Exception as e: return {'rows':[], 'count':0, 'total':0, 'error':f'Explorer query failed: {e}'}
    rows=[{'rank':i,'player_id':r['player_id'],'player_name':r['player_name'],'season':r['season'],'season_label':r['season'],'xValue':r['x_value'],'yValue':r['y_value'],'x_percentile':r['x_percentile'],'y_percentile':r['y_percentile'],'headshot_url':None} for i,r in enumerate(raw,1)]
    total=len(rows); cap=max(1,min(int(limit or 100),100))
    season_rows=c.execute("SELECT DISTINCT season, season_end_year, era FROM percentile WHERE statistic=? ORDER BY season_end_year ASC",(xsrc,)).fetchall()
    season_options=[{'value':r['season'],'label':r['season']} for r in season_rows if not era or str(r['era'])==str(era)]
    return {'rows':rows[:cap],'count':min(total,cap),'total':total,'population_total':total,'available_bounds':{'xmin':min((float(r['xValue']) for r in rows),default=None),'xmax':max((float(r['xValue']) for r in rows),default=None),'ymin':min((float(r['yValue']) for r in rows),default=None),'ymax':max((float(r['yValue']) for r in rows),default=None)},'x_statistic':xs,'y_statistic':ys,'season':season or 'Historical Percentile','season_type':'Regular Season','scope':'single','era':era or '','ranked_by':'x','season_options':season_options,'rank_direction':'desc','public_layer':True}

def teams(season='',season_type='Regular Season',era=''):
    c=conn()
    if c is None:return {'rows':[],'count':0,'ready':False}
    w=['season_type=?']; p=[season_type]
    if season and season not in {'All','all','Historical Percentile'}: w.append('season=?'); p.append(season)
    if era and era not in {'All','all'}: w.append('season BETWEEN ? AND ?'); p.extend([]) # era filtered below in Python to avoid date parsing SQL complexity
    rows=[json.loads(r['payload']) for r in c.execute(f"SELECT payload FROM teams WHERE {' AND '.join(w[:1])}",p[:1]).fetchall()]
    if season and season not in {'All','all','Historical Percentile'}: rows=[r for r in rows if str(r.get('Season'))==str(season)]
    if era and era not in {'All','all'}: rows=[r for r in rows if era_for(r.get('Season'))==era]
    return {'rows':rows,'count':len(rows),'season':season or 'All','season_type':season_type,'public_layer':True}
