import json, math, re, shutil, itertools, py_compile
from pathlib import Path
import numpy as np
import pandas as pd

BASE=Path('/mnt/data/fix21/NBA_Per75_Website240')
OUT=Path('/mnt/data/peak22_clean/NBA_Per75_Website240')
if OUT.exists(): shutil.rmtree(OUT)
shutil.copytree(BASE,OUT)

sdi=pd.read_csv(OUT/'local_api/cache/regular_sdi_v4_wowy_rts_player_seasons.csv')
prof=pd.read_csv('/mnt/data/base239/final239/player_profiles_v1/player_season_profiles.csv', low_memory=False)
wowy=pd.read_csv('/mnt/data/base239/final239/data/player_wowy_statistics_v1.csv')
for d in (sdi,prof,wowy): d['Player_ID']=d['Player_ID'].astype(str).str.strip()
sdi['__year']=pd.to_numeric(sdi['SeasonEndYear'],errors='coerce')
prof['__year']=pd.to_numeric(prof['SeasonEndYear'],errors='coerce')
wowy['__year']=pd.to_numeric(wowy['SeasonEndYear'],errors='coerce')
prof=prof[prof['Season_Type'].astype(str).str.casefold().eq('regular season')].copy()
prof['G']=pd.to_numeric(prof['G'],errors='coerce'); prof['MP']=pd.to_numeric(prof['MP'],errors='coerce')
sched=prof.groupby('__year')['G'].max().to_dict()
prof=prof[(prof['G']>=prof['__year'].map(lambda y: math.ceil(.60*float(sched.get(y,82))) if pd.notna(y) else 999)) & (prof['MP']>=1400)].copy()
prof=prof.sort_values(['Player_ID','__year','MP'],ascending=[True,True,False]).drop_duplicates(['Player_ID','__year'])
wowy=wowy.drop_duplicates(['Player_ID','__year'])
prof=prof.merge(wowy[['Player_ID','__year','WOWY_Offense','WOWY_Defense','WOWY_Net']],on=['Player_ID','__year'],how='left')
sdi=sdi.sort_values(['Player_ID','__year','MP'],ascending=[True,True,False]).drop_duplicates(['Player_ID','__year'])
q=sdi.merge(prof[['Player_ID','__year']],on=['Player_ID','__year'],how='inner')
q['SDI_v4_WOWY']=pd.to_numeric(q['SDI_v4_WOWY'],errors='coerce')
q=q.dropna(subset=['SDI_v4_WOWY']).copy()

records=[]
for pid,g in q.groupby('Player_ID',sort=False):
    g=g.sort_values('__year').drop_duplicates('__year').reset_index(drop=True)
    by={int(r['__year']):r for _,r in g.iterrows()}
    years=sorted(by); candidates=[]
    # Only two candidate types are legal:
    # (1) five consecutive qualifying calendar seasons; OR
    # (2) six calendar years containing exactly five qualifying seasons and
    #     exactly one non-qualifying season. A qualifying season is never skipped.
    for start in years:
        yrs=tuple(range(start,start+5))
        if all(y in by for y in yrs):
            score=float(np.mean([float(by[y]['SDI_v4_WOWY']) for y in yrs]))
            candidates.append((score,yrs))
    for start in range(min(years), max(years)-4):
        span=list(range(start,start+6))
        present=[y for y in span if y in by]
        if len(present)!=5: continue
        if len([y for y in span if y not in by])!=1: continue
        if any(b-a>2 for a,b in zip(present,present[1:])): continue
        yrs=tuple(present)
        score=float(np.mean([float(by[y]['SDI_v4_WOWY']) for y in yrs]))
        candidates.append((score,yrs))
    if not candidates: continue
    score,yrs=max(candidates,key=lambda z:(round(z[0],12),z[1][-1],z[1][0]))
    first=by[yrs[0]]
    records.append({'Player_ID':pid,'Player':re.sub(r'\*+','',str(first['Player'])).strip(),'peak_start_year':yrs[0],'peak_end_year':yrs[-1], 'peak_seasons':[by[y]['Season'] for y in yrs], 'peak_sdi':score,'total_games':sum(float(by[y]['G']) for y in yrs),'total_minutes':sum(float(by[y]['MP']) for y in yrs),'_years':yrs})
print('candidate players:',len(records))

REG_STATS=['PTS_per75','FG_per75','FGA_per75','3P_per75','3PA_per75','2P_per75','2PA_per75','FT_per75','FTA_per75','ORB_per75','DRB_per75','TRB_per75','AST_per75','STL_per75','BLK_per75','TOV_per75','PF_per75','FG_pct','2P_pct','3P_pct','FT_pct','TS_pct','FTr','3PAr','rTS','WOWY_Offense','WOWY_Defense','WOWY_Net','PER','BPM','OBPM','DBPM','VORP','WS/48','OWS','DWS','OREB_pct','AST_pct','STL_pct','BLK_pct','TOV_pct','AST_TOV','DREB_pct']
raw={'PTS_per75':'PTS_raw','FG_per75':'FG_raw','FGA_per75':'FGA_raw','3P_per75':'3P_raw','3PA_per75':'3PA_raw','2P_per75':'2P_raw','2PA_per75':'2PA_raw','FT_per75':'FT_raw','FTA_per75':'FTA_raw','ORB_per75':'ORB_raw','DRB_per75':'DRB_raw','TRB_per75':'TRB_raw','AST_per75':'AST_raw','STL_per75':'STL_raw','BLK_per75':'BLK_raw','TOV_per75':'TOV_raw','PF_per75':'PF_raw'}
def f(v):
    try:
        x=float(v); return x if math.isfinite(x) else math.nan
    except: return math.nan

def aggregate(rows):
    out={}; poss=[f(r.get('Estimated_Possessions')) for r in rows]; mp=[f(r.get('MP')) for r in rows]
    for stat,rc in raw.items():
        num=den=0
        for r,p in zip(rows,poss):
            x=f(r.get(rc))
            if not math.isnan(x) and not math.isnan(p) and p>0: num+=x; den+=p
        out[stat]=num/den*75 if den else math.nan
    def ratio(nc,dc):
        n=d=0; ok=False
        for r in rows:
            a,b=f(r.get(nc)),f(r.get(dc))
            if not math.isnan(a) and not math.isnan(b): n+=a; d+=b; ok=True
        return n/d if ok and d>0 else math.nan
    out['FG_pct']=ratio('FG_raw','FGA_raw'); out['2P_pct']=ratio('2P_raw','2PA_raw'); out['3P_pct']=ratio('3P_raw','3PA_raw'); out['FT_pct']=ratio('FT_raw','FTA_raw')
    fga=ratio('FGA_raw','FGA_raw')
    FGA=sum(f(r.get('FGA_raw')) for r in rows if not math.isnan(f(r.get('FGA_raw')))); FTA=sum(f(r.get('FTA_raw')) for r in rows if not math.isnan(f(r.get('FTA_raw')))); PTS=sum(f(r.get('PTS_raw')) for r in rows if not math.isnan(f(r.get('PTS_raw')))); TPA=sum(f(r.get('3PA_raw')) for r in rows if not math.isnan(f(r.get('3PA_raw'))))
    out['TS_pct']=PTS/(2*(FGA+.44*FTA)) if FGA+.44*FTA>0 else math.nan; out['FTr']=FTA/FGA if FGA>0 else math.nan; out['3PAr']=TPA/FGA if FGA>0 else math.nan
    def mpavg(c):
        n=d=0
        for r,m in zip(rows,mp):
            x=f(r.get(c))
            if not math.isnan(x) and not math.isnan(m) and m>0: n+=x*m; d+=m
        return n/d if d else math.nan
    for stat in ['rTS','WOWY_Offense','WOWY_Defense','WOWY_Net','PER','BPM','OBPM','DBPM','OREB_pct','AST_pct','STL_pct','BLK_pct','TOV_pct','DREB_pct']: out[stat]=mpavg(stat)
    out['WS/48']=mpavg('WS/48.1')
    ast=sum(f(r.get('AST_raw')) for r in rows if not math.isnan(f(r.get('AST_raw')))); tov=sum(f(r.get('TOV_raw')) for r in rows if not math.isnan(f(r.get('TOV_raw')))); out['AST_TOV']=ast/tov if tov>0 else math.nan
    for stat in ['OWS','DWS','VORP']:
        a=[f(r.get(stat)) for r in rows]; a=[x for x in a if not math.isnan(x)]; out[stat]=sum(a) if a else math.nan
    return out

prof_map={(str(r['Player_ID']),int(r['__year'])):r.to_dict() for _,r in prof.iterrows() if pd.notna(r['__year'])}
q_map={(str(r['Player_ID']),int(r['__year'])):r.to_dict() for _,r in q.iterrows() if pd.notna(r['__year'])}
for rec in records:
    keys=[(rec['Player_ID'],y) for y in rec['_years']]
    rows=[prof_map[k] for k in keys]
    out=aggregate(rows)
    qrows=[q_map[k] for k in keys]
    for cat in ['scoring_volume','scoring_efficiency','creation_playmaking','rebounding','defense','impact_value']:
        a=[f(r.get('SDI_'+cat)) for r in qrows]; a=[x for x in a if not math.isnan(x)]; out['peak_SDI_'+cat]=sum(a)/len(a) if a else math.nan
        c=[f(r.get('SDI_'+cat+'_Coverage')) for r in qrows]; c=[x for x in c if not math.isnan(x)]; out['peak_SDI_'+cat+'_Coverage']=sum(c)/len(c) if c else math.nan
    c=[f(r.get('SDI_Category_Coverage')) for r in qrows]; c=[x for x in c if not math.isnan(x)]; out['peak_sdi_coverage']=sum(c)/len(c) if c else 1.0
    rec['statistics']=out

# Peak-context percentiles.
def pct(vals,higher=True):
    s=pd.Series(vals,dtype=float); out=pd.Series(np.nan,index=s.index); v=s.notna(); n=int(v.sum())
    if n==1: out.loc[v]=100.; return out
    if n==0:return out
    ranks=s.loc[v].rank(method='average',ascending=higher); out.loc[v]=100*(n-ranks)/(n-1); return out
for stat in REG_STATS:
    vals=[r['statistics'].get(stat,math.nan) for r in records]; p=pct(vals,higher=stat not in {'TOV_per75','PF_per75','TOV_pct'})
    for i,r in enumerate(records): r['statistics'][stat+'__percentile']=None if pd.isna(p.iloc[i]) else float(p.iloc[i])
p=pct([r['peak_sdi'] for r in records],True)
for i,r in enumerate(records): r['peak_sdi_percentile']=float(p.iloc[i])
for r in records: r.pop('_years',None)

outdir=OUT/'data/precomputed_5_year_peak'; outdir.mkdir(parents=True,exist_ok=True)
meta={'version':'regular_profile_peaks_wowy_rts_v1','player_count':len(records),'methodology':'Five qualifying regular-season seasons; each >=60% team games and >=1400 minutes; selected five fit within max six consecutive calendar seasons, at most one skipped/non-qualifying season and no two-season gap; highest mean season SDI using current WOWY-aware SDI v4 wins; displayed statistics aggregated from underlying totals/attempts/possessions rather than averaged season averages.','formula':'SDI v4 WOWY: Scoring Volume 20%, Defense 20%, Rebounding 10.5%, Creation & Playmaking 18%, Scoring Efficiency 18%, Impact & Value 13.5%; Scoring Efficiency Overall Efficiency 100% rTS; Creation Ball Security 100% AST:TOV; WOWY Offense 30% Creation, WOWY Defense 40% Defense, WOWY Net 100% Impact & Value.','selection_rules':{'min_games_fraction':0.60,'min_minutes':1400,'qualifying_seasons':5,'max_span_calendar_years':6,'max_year_gap':2,'selection_metric':'mean season SDI_v4_WOWY'},'players':records}
json.dump(meta,open(outdir/'regular_profile_peaks_wowy_rts_v1.json','w',encoding='utf8'),allow_nan=True,separators=(',',':'))
rows=[]
for r in records:
    row={k:r[k] for k in ['Player_ID','Player','peak_start_year','peak_end_year','peak_sdi','peak_sdi_percentile','total_games','total_minutes']}; row['peak_seasons']=' | '.join(r['peak_seasons']); row.update(r['statistics']); rows.append(row)
pd.DataFrame(rows).to_csv(outdir/'regular_profile_peaks_wowy_rts_v1.csv',index=False)

api=OUT/'local_api/nba_per75_local_api.py'; text=api.read_text(encoding='utf8'); text=text.replace('regular_profile_peaks_wowy_canonical_v1.json','regular_profile_peaks_wowy_rts_v1.json').replace('__precomputed_regular_peak_profiles_v7_sdi_v4_authoritative__','__precomputed_regular_peak_profiles_wowy_rts_v1__').replace('"source":"precomputed_5_year_peak_authoritative_v6"','"source":"precomputed_5_year_peak_wowy_rts_v1"').replace('"peak_cache_version":"regular_profile_peaks_wowy_canonical_v1"','"peak_cache_version":"regular_profile_peaks_wowy_rts_v1"'); api.write_text(text,encoding='utf8'); py_compile.compile(str(api),doraise=True)

# Reproducible builder and install notes.
shutil.copy2('/mnt/data/build_peak22_clean.py',OUT/'analysis_build_regular_peak_wowy_rts_v1.py')
(OUT/'REGULAR_5_YEAR_PEAK_WOWY_RTS_FIX_22_INSTALL.txt').write_text('''WEBSITE240 — REGULAR 5-YEAR PEAK WOWY + CURRENT SDI FIX 22\n\nReplaces the obsolete regular 5-Year Peak cache with a league-wide offline cache selected from the current WOWY-aware season SDI layer.\n\nSelection: five qualifying regular seasons; >=60% team games and >=1400 minutes each; max six-calendar-year span; at most one skipped/non-qualifying season; no two-season gap; no Era Average threshold; highest mean five-season SDI wins.\n\nCurrent SDI: Scoring Volume 20%, Defense 20%, Rebounding 10.5%, Creation & Playmaking 18%, Scoring Efficiency 18%, Impact & Value 13.5%. Efficiency Overall = 100% rTS. Creation Ball Security = 100% AST:TOV. WOWY Offense = 30% Creation, WOWY Defense = 40% Defense, WOWY Net = 100% Impact & Value.\n\nDisplayed peak statistics are aggregated from underlying totals/attempts/possessions. rTS and WOWY rates are MP-weighted; AST:TOV uses total recorded AST/TOV.\n\nValidation: Giannis Antetokounmpo remains 2018-2022. Wilt Chamberlain changes from 1964-1968 to 1960-1964 under the current WOWY-aware season SDI selection.\n\nDoes not modify playoff 5-Year Peak or the separate seasonal 2PA display issue.\n''',encoding='utf8')

for nm in ['Wilt Chamberlain','Giannis Antetokounmpo']:
    hit=next(r for r in records if r['Player'].casefold()==nm.casefold())
    print(nm,hit['peak_start_year'],hit['peak_end_year'],hit['peak_seasons'],hit['peak_sdi'],hit['peak_sdi_percentile'])

zipbase=Path('/mnt/data/Website240_REGULAR_5_YEAR_PEAK_WOWY_RTS_FIX_22')
shutil.make_archive(str(zipbase),'zip',OUT.parent,OUT.name)
print('ZIP_SIZE',zipbase.with_suffix('.zip').stat().st_size)
