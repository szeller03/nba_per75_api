"""Build the precomputed Big Board cache for Website240 Fix 38.

This is a one-time BUILD step. It reads the existing canonical public SQLite
layer and its qualification sidecar, materializes eligible Big Board rows, and
stores them in an indexed cache. No statistical methodology is recalculated.
"""
from pathlib import Path
import sqlite3, os, time, shutil

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT/'data'/'public'/'per75_public.sqlite3'
ELIG = ROOT/'data'/'public'/'board_eligibility.sqlite3'
OUT = ROOT/'data'/'public'/'big_board_cache_v38.sqlite3'

STATS = {
 'PTS_per75':'basic','FG_per75':'basic','FGA_per75':'basic','3P_per75':'basic','3PA_per75':'basic','2P_per75':'basic','2PA_per75':'basic',
 'FT_per75':'basic','FTA_per75':'basic','ORB_per75':'basic','DRB_per75':'basic','TRB_per75':'basic','AST_per75':'basic','STL_per75':'basic',
 'BLK_per75':'basic','TOV_per75':'basic','PF_per75':'basic','FG_pct':'fg_pct','2P_pct':'basic','3P_pct':'threep_pct','FT_pct':'ft_pct','TS_pct':'ts_pct',
 'FTr':'basic','3PAr':'basic','rTS':'advanced','PER':'advanced','BPM':'basic','OBPM':'basic','DBPM':'advanced','VORP':'basic','WS/48':'advanced','OWS':'basic','DWS':'advanced',
 'OREB_pct':'advanced','AST_pct':'advanced','STL_pct':'advanced','BLK_pct':'advanced','TOV_pct':'advanced','AST_TOV':'basic','DREB_pct':'advanced',
 'WOWY_Offense':'basic','WOWY_Defense':'basic','WOWY_Net':'basic'
}

# Existing canonical sidecar eligibility columns. Keep this mapping aligned with
# public_data_layer.py; this controls population only, never statistic values.

def main():
    if not DB.exists():
        raise SystemExit(f'Missing public database: {DB}')
    if not ELIG.exists():
        raise SystemExit(f'Missing eligibility database: {ELIG}')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        backup=OUT.with_suffix('.v38.bak.sqlite3')
        try: backup.unlink()
        except FileNotFoundError: pass
        shutil.copy2(OUT, backup)
        OUT.unlink()

    src=sqlite3.connect(f'file:{DB}?mode=ro&immutable=1', uri=True)
    src.row_factory=sqlite3.Row
    src.execute('ATTACH DATABASE ? AS elig', (str(ELIG),))
    dst=sqlite3.connect(OUT)
    dst.execute('PRAGMA journal_mode=OFF')
    dst.execute('PRAGMA synchronous=OFF')
    dst.execute('PRAGMA temp_store=MEMORY')
    dst.execute('''CREATE TABLE rows (
        statistic TEXT NOT NULL,
        player_id TEXT,
        player_name TEXT,
        season TEXT,
        season_end_year INTEGER,
        value REAL,
        season_percentile REAL,
        era_percentile REAL,
        historical_percentile REAL,
        era TEXT
    )''')
    dst.execute('CREATE INDEX idx_board_v38_lookup ON rows(statistic, season_end_year, season, historical_percentile DESC)')
    dst.execute('CREATE INDEX idx_board_v38_hist ON rows(statistic, historical_percentile DESC)')
    dst.execute('CREATE INDEX idx_board_v38_season_pct ON rows(statistic, season, season_percentile DESC)')
    dst.execute('CREATE INDEX idx_board_v38_era_pct ON rows(statistic, era, era_percentile DESC)')
    dst.execute('CREATE INDEX idx_board_v38_player ON rows(statistic, player_name)')
    dst.execute('CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)')

    started=time.perf_counter(); total=0
    # WOWY is a first-class statistic layer and is NOT stored in the generic
    # percentile table. Read its authoritative values/percentiles directly from
    # the existing player_wowy_statistics_v1.csv shipped with this build. This
    # preserves the established WOWY methodology while making Big Board delivery
    # precomputed just like the other statistics.
    wowy_path = ROOT/'local_api'/'cache'/'player_wowy_statistics_v1.csv'
    wowy_df = None
    if wowy_path.exists():
        import pandas as pd
        wowy_df = pd.read_csv(wowy_path, low_memory=False)
        wowy_df['Player_ID']=wowy_df['Player_ID'].astype(str).str.strip()
        wowy_df['Player']=wowy_df['Player'].astype(str).str.strip()
        wowy_df['Season']=wowy_df['Season'].astype(str).str.strip()
        wowy_df['SeasonEndYear']=pd.to_numeric(wowy_df['SeasonEndYear'], errors='coerce')

    for stat, gate in STATS.items():
        if stat.startswith('WOWY_'):
            if wowy_df is None:
                print(f'{stat}: 0 rows (missing {wowy_path})')
                continue
            value_col=stat
            pct_col=stat+'_Percentile'
            work=wowy_df.copy()
            # Existing source explicitly marks the PER-75-qualified population.
            if 'PER75_Qualified' in work.columns:
                work=work.loc[work['PER75_Qualified'].fillna(False).astype(bool)].copy()
            work[value_col]=pd.to_numeric(work[value_col], errors='coerce')
            work[pct_col]=pd.to_numeric(work[pct_col], errors='coerce')
            work=work.dropna(subset=[value_col,pct_col,'SeasonEndYear'])
            # WOWY source provides historical percentiles. Era/season percentiles
            # are not silently invented; for this cache they use the authoritative
            # WOWY percentile for the ranking context currently supported by the
            # public Big Board.
            rows=[]
            for _,r in work.iterrows():
                pct=float(r[pct_col])
                rows.append((stat,r['Player_ID'],r['Player'],r['Season'],int(r['SeasonEndYear']),float(r[value_col]),pct,pct,pct,''))
            dst.executemany('INSERT INTO rows VALUES (?,?,?,?,?,?,?,?,?,?)',rows)
            total += len(rows)
            print(f'{stat}: {len(rows):,} rows [authoritative WOWY source]')
            continue

        elig_col = gate
        # For the historical 2PA proxy, the existing public layer maps it to FGA
        # before querying, so cache FGA rows under 2PA as well for season-era compatibility.
        source_stat = 'FGA_per75' if stat == '2PA_per75' else stat
        sql=f'''SELECT p.player_id,p.player_name,p.season,p.season_end_year,p.value,
                       p.season_percentile,p.era_percentile,p.historical_percentile,p.era
                FROM percentile p
                JOIN elig.eligibility e
                  ON e.player_id=p.player_id AND e.season=p.season AND e.{elig_col}=1
                WHERE p.statistic=?'''
        rows=src.execute(sql,(source_stat,)).fetchall()
        batch=[]
        for r in rows:
            batch.append((stat,r['player_id'],r['player_name'],r['season'],r['season_end_year'],r['value'],r['season_percentile'],r['era_percentile'],r['historical_percentile'],r['era']))
            if len(batch)>=10000:
                dst.executemany('INSERT INTO rows VALUES (?,?,?,?,?,?,?,?,?,?)',batch); total+=len(batch); batch.clear()
        if batch:
            dst.executemany('INSERT INTO rows VALUES (?,?,?,?,?,?,?,?,?,?)',batch); total+=len(batch)
        print(f'{stat}: {len(rows):,} rows')
    dst.executemany('INSERT INTO meta VALUES (?,?)', [('version','39'),('source',str(DB)),('built_at',time.strftime('%Y-%m-%dT%H:%M:%S')),('rows',str(total))])
    dst.commit(); dst.close(); src.close()
    print(f'Big Board cache ready: {total:,} rows in {time.perf_counter()-started:.1f}s')
    print(f'Output: {OUT}')

if __name__=='__main__': main()
