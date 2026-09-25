from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / 'data' / 'regular_career_sdi_v4_wowy_rts.csv'
OUT = ROOT / 'data' / 'CAREER_DEFENSE_TOP25_AUDIT.json'

NAME_CHECKS = [
    'Rudy Gobert','Bill Russell','Dikembe Mutombo','Kevin Garnett','David Robinson',
    'Hakeem Olajuwon','Tim Duncan','Ben Wallace','Wilt Chamberlain','Kareem Abdul-Jabbar',
    'Dennis Rodman','Draymond Green','Dwight Howard','Patrick Ewing','Artis Gilmore',
    'Scottie Pippen','Elvin Hayes','Wes Unseld','Nate Thurmond','Alonzo Mourning'
]

def pick(df, names):
    col = next((c for c in ['Player','player','PLAYER','Player_Name','player_name'] if c in df.columns), None)
    if col is None: raise RuntimeError('Could not find player-name column.')
    return col

def main():
    if not CSV.exists():
        raise FileNotFoundError(f'Expected {CSV}. Put this script in the project root and run it there.')
    df = pd.read_csv(CSV, low_memory=False)
    pcol = pick(df, NAME_CHECKS)
    dcol = next((c for c in ['Career_defense','Career_Defense','career_defense'] if c in df.columns), None)
    if dcol is None:
        raise RuntimeError('Could not find Career_defense column.')
    df[dcol] = pd.to_numeric(df[dcol], errors='coerce')
    out = df.dropna(subset=[dcol]).sort_values([dcol, pcol], ascending=[False, True], kind='mergesort').copy()
    top = out.head(25)
    named = out[out[pcol].astype(str).str.lower().isin({n.lower() for n in NAME_CHECKS})].head(50)
    rows = []
    for i, (_, r) in enumerate(top.iterrows(), 1):
        rows.append({'rank': i, 'player': r[pcol], 'career_defense': float(r[dcol])})
    checks = []
    for _, r in named.iterrows():
        checks.append({'player': r[pcol], 'career_defense': float(r[dcol])})
    result = {
        'version':'Career_Defense_Top25_Audit_v1',
        'source':str(CSV),
        'rows_with_career_defense':int(len(out)),
        'top_25':rows,
        'named_player_checks':checks,
        'method':'Sort the rebuilt canonical Career_defense column descending; no recalculation.'
    }
    OUT.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))

if __name__ == '__main__': main()
