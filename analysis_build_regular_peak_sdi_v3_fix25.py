import math, re, shutil, json, py_compile
from pathlib import Path
import pandas as pd, numpy as np

ROOT=Path('/mnt/data/peak24/NBA_Per75_Website240')
SDI=ROOT/'local_api/cache/regular_sdi_v4_wowy_rts_player_seasons.csv'
PROF=Path('/mnt/data/base239/final239/player_profiles_v1/player_season_profiles.csv')
WOWY=Path('/mnt/data/base239/final239/data/player_wowy_statistics_v1.csv')

sdi=pd.read_csv(SDI,low_memory=False); prof=pd.read_csv(PROF,low_memory=False); wowy=pd.read_csv(WOWY,low_memory=False)
for d in (sdi,prof,wowy): d['Player_ID']=d['Player_ID'].astype(str).str.strip()
for d in (sdi,prof,wowy): d['__year']=pd.to_numeric(d['SeasonEndYear'],errors='coerce')
prof=prof[prof['Season_Type'].astype(str).str.casefold().eq('regular season')].copy()
prof['G']=pd.to_numeric(prof['G'],errors='coerce'); prof['MP']=pd.to_numeric(prof['MP'],errors='coerce')
sched=prof.groupby('__year')['G'].max().to_dict()
# Project rule: season qualifies iff BOTH 60% games AND 1400 MP.
prof['__min_games']=prof['__year'].map(lambda y: math.ceil(.60*float(sched.get(y,82))) if pd.notna(y) else 999)
prof=prof[(prof['G']>=prof['__min_games']) & (prof['MP']>=1400)].copy()
prof=prof.sort_values(['Player_ID','__year','MP'],ascending=[True,True,False]).drop_duplicates(['Player_ID','__year'])
wowy=wowy.drop_duplicates(['Player_ID','__year'])
prof=prof.merge(wowy[['Player_ID','__year','WOWY_Offense','WOWY_Defense','WOWY_Net']],on=['Player_ID','__year'],how='left')
sdi=sdi.sort_values(['Player_ID','__year','MP'],ascending=[True,True,False]).drop_duplicates(['Player_ID','__year'])
q=sdi.merge(prof[['Player_ID','__year']],on=['Player_ID','__year'],how='inner')
q['SDI_v4_WOWY']=pd.to_numeric(q['SDI_v4_WOWY'],errors='coerce'); q=q.dropna(subset=['SDI_v4_WOWY']).copy()

# STRICT peak selection: either 5 consecutive qualifying seasons, OR a 6-calendar-year span
# containing exactly 5 qualifying seasons and exactly 1 non-qualifying/missing season.
records=[]
for pid,g in q.groupby('Player_ID',sort=False):
    g=g.sort_values('__year').drop_duplicates('__year').reset_index(drop=True)
    by={int(r['__year']):r for _,r in g.iterrows()}; years=sorted(by); candidates=[]
    for start in range(min(years),max(years)+1):
        span5=[y for y in range(start,start+5) if y in by]
        span6=[y for y in range(start,start+6) if y in by]
        if len(span5)==5:
            candidates.append(tuple(span5))
        if len(span6)==5 and len(set(span6))==5:
            candidates.append(tuple(span6))
    # Deduplicate; a qualifying season can never be skipped. Six-year candidate must have one absent year.
    candidates=sorted(set(candidates))
    # Validate all candidate years are exactly the qualifying seasons in the span.
    valid=[]
    for yrs in candidates:
        if len(yrs)==5:
            if yrs[-1]-yrs[0] == 4:
                valid.append(yrs)
            elif yrs[-1]-yrs[0] == 5:
                # exactly one missing calendar year
                span=set(range(yrs[0],yrs[-1]+1))
                if len(span-set(yrs))==1: valid.append(yrs)
    for yrs in valid:
        score=float(np.mean([float(by[y]['SDI_v4_WOWY']) for y in yrs]))
        candidatescore=(score,yrs[-1],yrs[0])
        # store score tuple
        pass
    if not valid: continue
    best=max(valid,key=lambda yrs:(round(float(np.mean([float(by[y]['SDI_v4_WOWY']) for y in yrs])),12),yrs[-1],yrs[0]))
    score=float(np.mean([float(by[y]['SDI_v4_WOWY']) for y in best]))
    first=by[best[0]]
    records.append({'Player_ID':pid,'Player':re.sub(r'\*+','',str(first['Player'])).strip(),'peak_start_year':best[0],'peak_end_year':best[-1],'peak_seasons':[by[y]['Season'] for y in best],'peak_sdi':score,'total_games':sum(float(by[y]['G']) for y in best),'total_minutes':sum(float(by[y]['MP']) for y in best),'_years':best})

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
        n=d=0
        for r in rows:
            a,b=f(r.get(nc)),f(r.get(dc))
            if not math.isnan(a) and not math.isnan(b): n+=a; d+=b
        return n/d if d>0 else math.nan
    out['FG_pct']=ratio('FG_raw','FGA_raw'); out['2P_pct']=ratio('2P_raw','2PA_raw'); out['3P_pct']=ratio('3P_raw','3PA_raw'); out['FT_pct']=ratio('FT_raw','FTA_raw')
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
        vals=[f(r.get(stat)) for r in rows if not math.isnan(f(r.get(stat)))]; out[stat]=sum(vals) if vals else math.nan
    return out
prof_map={(str(r['Player_ID']),int(r['__year'])):r.to_dict() for _,r in prof.iterrows() if pd.notna(r['__year'])}
q_map={(str(r['Player_ID']),int(r['__year'])):r.to_dict() for _,r in q.iterrows() if pd.notna(r['__year'])}
for rec in records:
    keys=[(rec['Player_ID'],y) for y in rec['_years']]; out=aggregate([prof_map[k] for k in keys]); qrows=[q_map[k] for k in keys]
    for cat in ['scoring_volume','scoring_efficiency','creation_playmaking','rebounding','defense','impact_value']:
        a=[f(r.get('SDI_'+cat)) for r in qrows if not math.isnan(f(r.get('SDI_'+cat)))]; out['peak_SDI_'+cat]=sum(a)/len(a) if a else math.nan
        c=[f(r.get('SDI_'+cat+'_Coverage')) for r in qrows if not math.isnan(f(r.get('SDI_'+cat+'_Coverage')))]; out['peak_SDI_'+cat+'_Coverage']=sum(c)/len(c) if c else math.nan
    c=[f(r.get('SDI_Category_Coverage')) for r in qrows if not math.isnan(f(r.get('SDI_Category_Coverage')))]; out['peak_sdi_coverage']=sum(c)/len(c) if c else 1.0; rec['statistics']=out

def pct(vals,higher=True):
    s=pd.Series(vals,dtype=float); out=pd.Series(np.nan,index=s.index); v=s.notna(); n=int(v.sum())
    if n==1: out.loc[v]=100.; return out
    if n==0:return out
    ranks=s.loc[v].rank(method='average',ascending=higher); out.loc[v]=100*(n-ranks)/(n-1); return out
for stat in REG_STATS:
    vals=[r['statistics'].get(stat,math.nan) for r in records]; p=pct(vals,higher=stat not in {'TOV_per75','PF_per75','TOV_pct'})
    for i,r in enumerate(records): r['statistics'][stat+'__percentile']=None if pd.isna(p.iloc[i]) else float(p.iloc[i])
p=pct([r['peak_sdi'] for r in records],True)
for i,r in enumerate(records): r['peak_sdi_percentile']=float(p.iloc[i]); r.pop('_years',None)

outdir=ROOT/'data/precomputed_5_year_peak'; outdir.mkdir(parents=True,exist_ok=True)
version='regular_profile_peaks_wowy_rts_v3_career_sdi'
meta={'version':version,'player_count':len(records),'methodology':'Strict canonical regular 5-Year Peak. Every included season must itself qualify at >=60% of that season schedule AND >=1400 MP. Valid windows are only (A) five consecutive qualifying calendar seasons, or (B) a six-calendar-year span containing exactly five qualifying seasons and exactly one non-qualifying/missing season. A qualifying season may never be skipped. No Era Average threshold. Peak statistics aggregate underlying totals/attempts/possessions rather than averaging season averages. Peak SDI selection uses mean authoritative season SDI v4 WOWY.','formula':'SDI v4 WOWY: Scoring Volume 20%, Defense 20%, Rebounding 10.5%, Creation & Playmaking 18%, Scoring Efficiency 18%, Impact & Value 13.5%; Scoring Efficiency Overall = 100% rTS; Creation Ball Security = 100% AST:TOV; WOWY Offense = 30% Creation; WOWY Defense = 40% Defense; WOWY Net = 100% Impact & Value.','selection_rules':{'min_games_fraction':0.60,'min_minutes':1400,'qualifying_seasons':5,'max_span_calendar_years':6,'exactly_one_nonqualifying_allowed_in_six_year_window':True,'qualifying_season_may_be_skipped':False,'selection_metric':'mean authoritative season SDI_v4_WOWY'},'players':records}
json.dump(meta,open(outdir/f'{version}.json','w',encoding='utf8'),allow_nan=True,separators=(',',':'))
rows=[]
for r in records:
    row={k:r[k] for k in ['Player_ID','Player','peak_start_year','peak_end_year','peak_sdi','peak_sdi_percentile','total_games','total_minutes']}; row['peak_seasons']=' | '.join(r['peak_seasons']); row.update(r['statistics']); rows.append(row)
pd.DataFrame(rows).to_csv(outdir/f'{version}.csv',index=False)

# Patch API to use the new cache/version. Keep existing career v3 logic intact.
api=ROOT/'local_api/nba_per75_local_api.py'; text=api.read_text(encoding='utf8')
for old,new in [('regular_profile_peaks_wowy_canonical_v1.json',f'{version}.json'),('regular_profile_peaks_wowy_rts_v1.json',f'{version}.json'),('regular_profile_peaks_wowy_rts_v2.json',f'{version}.json'),('regular_profile_peaks_wowy_rts_v3.json',f'{version}.json'),('precomputed_5_year_peak_authoritative_v6',f'precomputed_5_year_peak_{version}')]: text=text.replace(old,new)
api.write_text(text,encoding='utf8'); py_compile.compile(str(api),doraise=True)

# Validation report.
checks=[]
for name in ['Wilt Chamberlain','Giannis Antetokounmpo','Stephen Curry','Magic Johnson','LeBron James']:
    m=[r for r in records if r['Player'].casefold()==name.casefold()]
    if m:
        r=m[0]; checks.append((name,r['peak_start_year'],r['peak_end_year'],' | '.join(r['peak_seasons']),r['peak_sdi']))
print('PLAYERS',len(records))
for x in checks: print(*x,sep=' | ')

( ROOT/'REGULAR_5_YEAR_PEAK_SDI_V3_FIX_25_INSTALL.txt').write_text(f'''WEBSITE240 — REGULAR 5-YEAR PEAK SDI v3 / FIX 25\n\nThis patch is built on Career SDI v3 Fix 24 and replaces the regular-season 5-Year Peak cache.\n\nSTRICT PEAK RULE\n1. Every included season must meet the normal regular-season threshold: >=60% of that season's team games AND >=1400 minutes.\n2. Valid peak windows are ONLY: (A) five consecutive qualifying seasons; OR (B) a six-calendar-year span with exactly five qualifying seasons and exactly one non-qualifying/missing season.\n3. A season that qualifies CANNOT be skipped to improve the SDI score.\n4. No Era Average threshold.\n5. Peak statistics are aggregated from underlying totals/attempts/possessions.\n6. Peak selection metric is the mean authoritative season SDI v4 WOWY across the five included seasons.\n\nThe package contains the generated peak cache, the API patch, the reproducible builder, and this install note. It does not modify the playoff peak cache or the separate seasonal 2PA display issue.\n\nValidation targets from the build are included in the console output when the builder is rerun.\n''',encoding='utf8')
shutil.copy2('/mnt/data/build_peak24.py',ROOT/'analysis_build_regular_peak_sdi_v3_fix25.py')
