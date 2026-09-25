import argparse, json, re, zipfile, tempfile, shutil
from pathlib import Path
import pandas as pd


def season_label(end_year):
    return f"{end_year-1}-{str(end_year)[-2:]}"

def flatten(c):
    if isinstance(c, tuple):
        a=[str(x).strip() for x in c]
        return ' | '.join(x for x in a if x and not x.lower().startswith('unnamed'))
    return str(c).strip()

def find_table(html_path):
    for t in pd.read_html(html_path):
        if not isinstance(t.columns, pd.MultiIndex):
            continue
        top=[str(x).strip() for x in t.columns.get_level_values(0)]
        low=[str(x).strip() for x in t.columns.get_level_values(1)]
        if 'Offense Four Factors' in top and 'eFG%' in low and 'TOV%' in low and 'Defense Four Factors' in top:
            return t
    return None

def extract(html_path, end_year):
    t=find_table(html_path)
    if t is None:
        raise ValueError(f'No B-Ref Advanced/Four Factors table: {html_path}')
    out=[]
    for _,r in t.iterrows():
        team=r.get(('Unnamed: 1_level_0','Team'))
        efg=r.get(('Offense Four Factors','eFG%'))
        tov=r.get(('Offense Four Factors','TOV%'))
        if pd.isna(team):
            continue
        team_name=str(team).strip()
        if team_name.lower() == 'league average':
            continue
        if pd.isna(efg) or pd.isna(tov):
            # Older seasons can lack one or both offensive fields; don't invent values.
            continue
        out.append({'team':team_name, 'efgpct':float(efg)*100, 'tovpct':float(tov)})
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('source', help='cache directory or ZIP containing B-Ref HTML')
    ap.add_argument('--out', default='bref_offensive_four_factors_extracted.json')
    ap.add_argument('--csv', default='bref_offensive_four_factors_extracted.csv')
    args=ap.parse_args()
    src=Path(args.source)
    tmp=None
    if src.is_file() and src.suffix.lower()=='.zip':
        tmp=Path(tempfile.mkdtemp(prefix='bref_ff_'))
        with zipfile.ZipFile(src) as z: z.extractall(tmp)
        roots=[tmp/'cache', tmp]
        files=[]
        for root in roots:
            if root.exists(): files += list(root.rglob('https_www_basketball_reference_com_leagues_NBA_*_html.html'))
        files=sorted(set(files))
    else:
        files=sorted(src.rglob('https_www_basketball_reference_com_leagues_NBA_*_html.html'))
    maps={}; rows=[]; failed=[]
    for p in files:
        m=re.search(r'NBA_(\d+)_html\.html$',p.name)
        if not m: continue
        y=int(m.group(1)); season=season_label(y)
        try:
            vals=extract(p,y)
            maps[f'{season}|Regular Season']={v['team']: {'efgpct':v['efgpct'],'tovpct':v['tovpct']} for v in vals}
            for v in vals:
                rows.append({'season':season,'season_type':'Regular Season',**v})
            print(f'OK {season}: {len(vals)} teams')
        except Exception as e:
            failed.append({'file':str(p),'season':season,'error':str(e)})
            print(f'FAILED {season}: {e}')
    payload={'version':'offline-bref-offensive-four-factors-v1','source':'Basketball-Reference cached season summary Advanced Stats / Offense Four Factors','extract_only':['eFG%','TOV%'],'ftr_touched':False,'seasons':maps}
    Path(args.out).write_text(json.dumps(payload,indent=2,sort_keys=True),encoding='utf-8')
    pd.DataFrame(rows).to_csv(args.csv,index=False)
    print(f'\nCompleted season maps: {len(maps)}')
    print(f'Total team-season rows: {len(rows)}')
    print(f'Failed seasons: {len(failed)}')
    if failed: Path(Path(args.out).stem+'_failures.json').write_text(json.dumps(failed,indent=2),encoding='utf-8')
    if tmp: shutil.rmtree(tmp,ignore_errors=True)

if __name__=='__main__': main()
