"""Website240 Performance Fix 37: optimize public SQLite eligibility joins.

Run once from local_api while the API is stopped. This does not alter any
statistical values or eligibility rules; it only adds lookup indexes used by
public Big Board queries.
"""
from pathlib import Path
import sqlite3, time

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'data'/'public'/'per75_public.sqlite3'
ELIG=ROOT/'data'/'public'/'board_eligibility.sqlite3'

INDEXES = [
    ('idx_elig_player_season_basic', 'CREATE INDEX IF NOT EXISTS idx_elig_player_season_basic ON eligibility(player_id, season, basic)'),
    ('idx_elig_player_season_advanced', 'CREATE INDEX IF NOT EXISTS idx_elig_player_season_advanced ON eligibility(player_id, season, advanced)'),
    ('idx_elig_player_season_fg_pct', 'CREATE INDEX IF NOT EXISTS idx_elig_player_season_fg_pct ON eligibility(player_id, season, fg_pct)'),
    ('idx_elig_player_season_ft_pct', 'CREATE INDEX IF NOT EXISTS idx_elig_player_season_ft_pct ON eligibility(player_id, season, ft_pct)'),
    ('idx_elig_player_season_threep_pct', 'CREATE INDEX IF NOT EXISTS idx_elig_player_season_threep_pct ON eligibility(player_id, season, threep_pct)'),
]

def main():
    if not ELIG.exists():
        print('board_eligibility.sqlite3 not found:', ELIG)
        return 1
    t=time.time()
    con=sqlite3.connect(ELIG)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA synchronous=NORMAL')
    cols={r[1] for r in con.execute('PRAGMA table_info(eligibility)').fetchall()}
    required={'player_id','season','basic','advanced','fg_pct','ft_pct','threep_pct'}
    missing=required-cols
    if missing:
        print('Eligibility schema missing columns:', sorted(missing))
        con.close(); return 2
    for name,sql in INDEXES:
        print('Ensuring',name)
        con.execute(sql)
    con.commit()
    con.execute('PRAGMA optimize')
    print('Indexes ready in %.2fs' % (time.time()-t))
    print('DB:', ELIG)
    con.close()
    return 0

if __name__=='__main__': raise SystemExit(main())
