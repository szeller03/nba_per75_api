"""Build Website240 Fix 44 Big Board materialized cache.
Copies values/percentiles from the existing public percentile database and the
existing authoritative WOWY CSV; qualification gates are copied, not recalculated.
"""
from pathlib import Path
import sqlite3,csv,time,shutil
ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'data/public/per75_public.sqlite3'; ELIG=ROOT/'data/public/board_eligibility.sqlite3'; WOWY=ROOT/'local_api/cache/player_wowy_statistics_v1.csv'; OUT=ROOT/'data/public/big_board_cache_v44.sqlite3'
STATS={
 'PTS_per75':'basic','FG_per75':'basic','FGA_per75':'basic','3P_per75':'basic','3PA_per75':'basic','2P_per75':'basic','2PA_per75':'basic','FT_per75':'basic','FTA_per75':'basic','ORB_per75':'basic','DRB_per75':'basic','TRB_per75':'basic','AST_per75':'basic','STL_per75':'basic','BLK_per75':'basic','TOV_per75':'basic','PF_per75':'basic','FG_pct':'fg_pct','2P_pct':'basic','3P_pct':'threep_pct','FT_pct':'ft_pct','TS_pct':'ts_pct','FTr':'basic','3PAr':'basic','rTS':'advanced','PER':'advanced','BPM':'basic','OBPM':'basic','DBPM':'advanced','VORP':'basic','WS/48':'advanced','OWS':'basic','DWS':'advanced','OREB_pct':'advanced','AST_pct':'advanced','STL_pct':'advanced','BLK_pct':'advanced','TOV_pct':'advanced','AST_TOV':'basic','DREB_pct':'advanced'}
WOWY_STATS=['WOWY_Offense','WOWY_Defense','WOWY_Net']
def era(s):
 try:y=int(str(s)[:4])
 except:return ''
 if y<=1969:return '1951-52_to_1969-70'
 if y<=1979:return '1970-71_to_1979-80'
 if y<=1989:return '1980-81_to_1989-90'
 if y<=1999:return '1990-91_to_1999-00'
 if y<=2009:return '2000-01_to_2009-10'
 if y<=2019:return '2010-11_to_2019-20'
 return '2020-21_to_2025-26'
def main():
 if not DB.exists():raise SystemExit(f'Missing {DB}')
 if not ELIG.exists():raise SystemExit(f'Missing {ELIG}')
 OUT.parent.mkdir(parents=True,exist_ok=True)
 if OUT.exists(): OUT.unlink()
 src=sqlite3.connect(f'file:{DB}?mode=ro&immutable=1',uri=True); src.row_factory=sqlite3.Row; src.execute('ATTACH DATABASE ? AS elig',(str(ELIG),))
 dst=sqlite3.connect(OUT); dst.execute('PRAGMA journal_mode=OFF');dst.execute('PRAGMA synchronous=OFF');dst.execute('PRAGMA temp_store=MEMORY')
 dst.execute('CREATE TABLE rows(statistic TEXT NOT NULL,player_id TEXT,player_name TEXT,season TEXT,season_end_year INTEGER,value REAL,season_percentile REAL,era_percentile REAL,historical_percentile REAL,era TEXT)')
 dst.execute('CREATE INDEX idx_b44_stat_hist ON rows(statistic,historical_percentile DESC,player_name)');dst.execute('CREATE INDEX idx_b44_stat_season ON rows(statistic,season,season_percentile DESC,player_name)');dst.execute('CREATE INDEX idx_b44_stat_era ON rows(statistic,era,era_percentile DESC,player_name)');dst.execute('CREATE INDEX idx_b44_stat_player ON rows(statistic,player_id)');dst.execute('CREATE INDEX idx_b44_stat_name ON rows(statistic,player_name)')
 dst.execute('CREATE TABLE season_options(season TEXT,season_end_year INTEGER)')
 seasons=src.execute('SELECT DISTINCT season,season_end_year FROM percentile ORDER BY season_end_year').fetchall();dst.executemany('INSERT INTO season_options VALUES (?,?)',[(r['season'],r['season_end_year']) for r in seasons])
 total=0;t=time.perf_counter()
 for stat,gate in STATS.items():
  source='FGA_per75' if stat=='2PA_per75' else stat
  rows=src.execute(f'''SELECT p.player_id,p.player_name,p.season,p.season_end_year,p.value,p.season_percentile,p.era_percentile,p.historical_percentile,p.era FROM percentile p JOIN elig.eligibility e ON e.player_id=p.player_id AND e.season=p.season AND e.{gate}=1 WHERE p.statistic=?''',(source,)).fetchall()
  dst.executemany('INSERT INTO rows VALUES (?,?,?,?,?,?,?,?,?,?)',[(stat,r['player_id'],r['player_name'],r['season'],r['season_end_year'],r['value'],r['season_percentile'],r['era_percentile'],r['historical_percentile'],r['era']) for r in rows]);total+=len(rows);print(f'{stat}: {len(rows):,}')
 if WOWY.exists():
  with WOWY.open(encoding='utf-8-sig',newline='') as f:
   for r in csv.DictReader(f):
    if str(r.get('PER75_Qualified','')).strip().casefold() not in {'true','1','yes'}:continue
    for stat in WOWY_STATS:
     val=r.get(stat);pct=r.get(stat+'_Percentile')
     try:v=float(val);p=float(pct)
     except:continue
     dst.execute('INSERT INTO rows VALUES (?,?,?,?,?,?,?,?,?,?)',(stat,r.get('Player_ID'),r.get('Player'),r.get('Season'),int(r.get('SeasonEndYear') or 0),v,p,p,p,era(r.get('Season'))));total+=1
  print('WOWY rows materialized.')
 dst.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)');dst.executemany('INSERT INTO meta VALUES (?,?)',[('version','44'),('rows',str(total)),('built_at',time.strftime('%Y-%m-%dT%H:%M:%S'))]);dst.commit();dst.close();src.close();print(f'Big Board v44 ready: {total:,} rows in {time.perf_counter()-t:.1f}s')
if __name__=='__main__':main()
