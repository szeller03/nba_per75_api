from pathlib import Path
import os
import sqlite3, json, re, math, time
import pandas as pd

ROOT=Path(os.environ.get('SOURCE_ROOT', str(Path(__file__).resolve().parents[1])))
OUT_ROOT=Path(__file__).resolve().parents[1]
OUT=OUT_ROOT/'data'/'public'/'per75_public.sqlite3'
MASTER=ROOT/'player_profiles_v1'/'player_season_profiles.csv'
PERCENTILES=ROOT/'player_analytics_v1_2_dreb'/'historical_percentiles_v2_1'/'player_season_percentiles_long_v2_1.csv'
IDENTITY=ROOT/'player_website_identity_v1'/'website_player_identity_v1.csv'
TEAMS=ROOT/'data'/'nba_per75_team_master_enriched.csv'

STAT_KEYS=['PTS_per75','FG_per75','FGA_per75','3P_per75','3PA_per75','2P_per75','2PA_per75','FT_per75','FTA_per75','ORB_per75','DRB_per75','TRB_per75','AST_per75','STL_per75','BLK_per75','TOV_per75','PF_per75','FG_pct','2P_pct','3P_pct','FT_pct','TS_pct','FTr','3PAr','rTS','PER','BPM','OBPM','DBPM','VORP','WS/48','OWS','DWS','OREB_pct','AST_pct','STL_pct','BLK_pct','TOV_pct','AST_TOV','DREB_pct','WOWY_Offense','WOWY_Defense','WOWY_Net','G','MP','Age','Team','Pos','Player_ID','Player']

def norm(s):
    return re.sub(r'[^a-z0-9]+',' ',str(s or '').casefold()).strip()

def clean(v):
    if pd.isna(v): return None
    if isinstance(v, (float,)) and not math.isfinite(v): return None
    return v.item() if hasattr(v,'item') else v

def main():
    t=time.time(); OUT.parent.mkdir(parents=True,exist_ok=True)
    for p in [OUT]:
        if p.exists(): p.unlink()
    conn=sqlite3.connect(OUT)
    conn.execute('PRAGMA journal_mode=OFF'); conn.execute('PRAGMA synchronous=OFF'); conn.execute('PRAGMA temp_store=MEMORY')
    conn.executescript('''
      CREATE TABLE players(player_id TEXT PRIMARY KEY, player_name TEXT, display_name TEXT, slug TEXT, nba_player_id TEXT, headshot_url TEXT, headshot_source TEXT, headshot_status TEXT, qualified_profile INTEGER, qualified_seasons INTEGER, search_key TEXT);
      CREATE INDEX idx_players_search ON players(search_key);
      CREATE TABLE seasons(player_id TEXT, season TEXT, season_end_year INTEGER, season_type TEXT, payload TEXT, PRIMARY KEY(player_id,season,season_type));
      CREATE INDEX idx_seasons_player_type ON seasons(player_id,season_type,season_end_year);
      CREATE TABLE percentile(player_id TEXT, player_name TEXT, season TEXT, season_end_year INTEGER, era TEXT, statistic TEXT, value REAL, season_percentile REAL, era_percentile REAL, historical_percentile REAL);
    ''')
    # recreate invalid index cleanly
    conn.execute('DROP INDEX IF EXISTS idx_pct_stat_season')
    conn.execute('CREATE INDEX idx_pct_stat_season ON percentile(statistic,season,season_end_year)')
    conn.execute('CREATE INDEX idx_pct_player ON percentile(player_id,season)')
    conn.execute('CREATE INDEX idx_pct_stat_hist ON percentile(statistic,historical_percentile)')

    ident=pd.read_csv(IDENTITY, dtype=str).fillna('')
    slug_to_pid={str(r.get('Player_Slug') or '').strip().replace('*',''):str(r.get('Player_ID') or '').strip() for _,r in ident.iterrows() if r.get('Player_ID')}
    name_to_pid={}
    for _,rr in ident.iterrows():
        if not rr.get('Player_ID'): continue
        k=norm(rr.get('Player') or rr.get('Display_Name') or '').replace('*','')
        if k and k not in name_to_pid: name_to_pid[k]=str(rr.get('Player_ID')).strip()
    for _,r in ident.iterrows():
        pid=r.get('Player_ID') or None
        if not pid: continue
        name=r.get('Player') or r.get('Display_Name') or ''
        conn.execute('INSERT OR REPLACE INTO players VALUES (?,?,?,?,?,?,?,?,?,?,?)',(
            pid,name,r.get('Display_Name') or name,r.get('Player_Slug') or '',r.get('NBA_Player_ID') or '',
            r.get('Headshot_URL') or '',r.get('Headshot_Source') or '',r.get('Headshot_Status') or '',
            1 if str(r.get('Qualified_Profile','')).lower() in {'1','true','yes'} else 0,
            int(float(r.get('Qualified_Seasons') or 0)) if str(r.get('Qualified_Seasons','')).strip() else 0,
            norm(name)+' '+norm(r.get('Display_Name') or '')+' '+norm(r.get('Player_Slug') or '')
        ))
    conn.commit()

    # Season payloads: one row per player-season, already aggregated by the source profile layer.
    df=pd.read_csv(MASTER, low_memory=False)
    keep=[c for c in STAT_KEYS if c in df.columns]
    for c in ['Season','SeasonEndYear','Season_Type']:
        if c not in keep: keep.append(c)
    df=df[keep].copy()
    for _,r in df.iterrows():
        raw_pid=str(r.get('Player_ID') or '').strip(); season=str(r.get('Season') or '').strip(); st=str(r.get('Season_Type') or 'Regular Season')
        pid=slug_to_pid.get(raw_pid.replace('*','')) or name_to_pid.get(norm(r.get('Player') or '').replace('*','')) or raw_pid
        if not pid or not season: continue
        payload={c:clean(r.get(c)) for c in keep if c not in {'Player_ID','Player','Season','SeasonEndYear','Season_Type'}}
        payload['Player_ID']=pid; payload['Player']=clean(r.get('Player')); payload['Season']=season; payload['SeasonEndYear']=clean(r.get('SeasonEndYear')); payload['Season_Type']=st
        # Historical 2PA display contract: before 1979-80, 2PA is literally FGA.
        if st=='Regular Season' and re.match(r'^19\d\d-\d\d$',season):
            y=int(season[:4])
            if y<1979 and payload.get('FGA_per75') is not None:
                payload['2PA_per75']=payload['FGA_per75']
                if payload.get('2PA_raw') is None and payload.get('FGA_raw') is not None:
                    payload['2PA_raw']=payload['FGA_raw']
        conn.execute('INSERT OR REPLACE INTO seasons VALUES (?,?,?,?,?)',(pid,season,int(r.get('SeasonEndYear') or 0),st,json.dumps(payload,separators=(',',':'))))
    conn.commit(); print('season rows',len(df))

    # Percentiles: bulk-transform with pandas, then write in chunks.
    pcts=pd.read_csv(PERCENTILES, low_memory=False, usecols=[
        'Player','Season','SeasonEndYear','Era','Statistic','Value',
        'Season_Percentile','Era_Percentile','Historical_Percentile'
    ])
    name_to_pid={}
    for _,rr in ident.iterrows():
        if not rr.get('Player_ID'): continue
        k=norm(rr.get('Player') or rr.get('Display_Name') or '').replace('*','')
        if k and k not in name_to_pid: name_to_pid[k]=str(rr.get('Player_ID')).strip()
    pcts['player_id']=pcts['Player'].map(lambda x:name_to_pid.get(norm(x).replace('*','')))
    pcts=pcts[pcts.player_id.notna()].copy()
    pcts['player_id']=pcts['player_id'].astype(str)
    pcts['SeasonEndYear']=pd.to_numeric(pcts['SeasonEndYear'],errors='coerce').fillna(0).astype(int)
    # Historical 2PA is exactly FGA before 1979-80: replace value + all percentile contexts.
    fga=pcts[pcts['Statistic'].eq('FGA_per75')][['player_id','Season','Value','Season_Percentile','Era_Percentile','Historical_Percentile']].rename(columns={
        'Value':'fga_value','Season_Percentile':'fga_sp','Era_Percentile':'fga_ep','Historical_Percentile':'fga_hp'})
    mask=pcts['Statistic'].eq('2PA_per75') & pcts['Season'].str[:4].str.isnumeric() & (pd.to_numeric(pcts['Season'].str[:4],errors='coerce')<1979)
    pcts=pcts.merge(fga,on=['player_id','Season'],how='left')
    pcts.loc[mask & pcts['fga_value'].notna(),'Value']=pcts.loc[mask & pcts['fga_value'].notna(),'fga_value']
    pcts.loc[mask & pcts['fga_sp'].notna(),'Season_Percentile']=pcts.loc[mask & pcts['fga_sp'].notna(),'fga_sp']
    pcts.loc[mask & pcts['fga_ep'].notna(),'Era_Percentile']=pcts.loc[mask & pcts['fga_ep'].notna(),'fga_ep']
    pcts.loc[mask & pcts['fga_hp'].notna(),'Historical_Percentile']=pcts.loc[mask & pcts['fga_hp'].notna(),'fga_hp']
    pcts=pcts[['player_id','Player','Season','SeasonEndYear','Era','Statistic','Value','Season_Percentile','Era_Percentile','Historical_Percentile']]
    pcts.columns=['player_id','player_name','season','season_end_year','era','statistic','value','season_percentile','era_percentile','historical_percentile']
    pcts.to_sql('percentile',conn,if_exists='append',index=False,chunksize=20000,method='multi')
    conn.commit(); print('percentile rows',len(pcts))

    # Team overview source.
    if TEAMS.exists():
        td=pd.read_csv(TEAMS, low_memory=False)
        conn.execute('CREATE TABLE teams(season TEXT, season_end_year INTEGER, season_type TEXT, team TEXT, payload TEXT)')
        conn.execute('CREATE INDEX idx_teams_season ON teams(season,season_type)')
        for _,r in td.iterrows():
            payload={str(c):clean(r[c]) for c in td.columns}
            conn.execute('INSERT INTO teams VALUES (?,?,?,?,?)',(str(r.get('Season') or ''),int(r.get('SeasonEndYear') or 0),str(r.get('Season_Type') or 'Regular Season'),str(r.get('Team') or ''),json.dumps(payload,separators=(',',':'))))
        conn.commit()
    conn.execute('PRAGMA optimize')
    conn.close(); print('built',OUT,OUT.stat().st_size/1e6,'MB', 'time',time.time()-t)

if __name__=='__main__': main()
