from pathlib import Path
import json, pandas as pd, numpy as np

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'; CACHE=ROOT/'local_api'/'cache'; CONFIG=ROOT/'config'
PCT=ROOT/'player_analytics_v1_2_dreb'/'historical_percentiles_v2_1'/'player_season_percentiles_long_v2_1.csv'
WOWY_SRC=Path('/mnt/data/WOWY_CANONICAL_PERCENTILE_LAYER_V1.csv')
BASE= CACHE/'regular_sdi_v4_player_seasons.csv'
OUT=CACHE/'regular_sdi_v4_wowy_player_seasons.csv'
SPEC_OUT=CONFIG/'statistical_index_v4_wowy_locked.json'
SITE_WOWY=DATA/'wowy_canonical_percentile_layer_v1.csv'

TOP={
 'scoring_volume':.20,'scoring_efficiency':.18,'creation_playmaking':.18,
 'rebounding':.105,'defense':.20,'impact_value':.135}

SPEC={
 'version':'SDI_v4_WOWY_locked', 'top_level_category_method':'weighted',
 'scoring_volume':{
  'Primary Scoring Output':{'weight':.35,'statistics':{'PTS_per75':1.0}},
  'Scoring Composition':{'weight':.65,'statistics':{'FGA_per75':.55,'FTA_per75':.45}},},
 'scoring_efficiency':{
  'Overall Efficiency':{'weight':.60,'statistics':{'TS_pct':.25,'rTS':.75}},
  'Component Efficiency':{'weight':.40,'statistics':{'2P_pct':.5,'3P_pct':.4,'FT_pct':.1}},},
 'creation_playmaking':{
  'Creation Output':{'weight':.385,'statistics':{'AST_per75':.8,'AST_pct':.2}},
  'Ball Security / Creation Cost':{'weight':.315,'statistics':{'AST_TOV':.6,'TOV_pct':.4}},
  'WOWY Offensive Impact':{'weight':.30,'statistics':{'WOWY_Offense':1.0}},},
 'rebounding':{
  'Rebounding Production':{'weight':.75,'statistics':{'ORB_per75':.45,'DRB_per75':.35,'TRB_per75':.2}},
  'Rebounding Rate':{'weight':.25,'statistics':{'OREB_pct':.45,'DREB_pct':.35,'TRB_pct':.2}},},
 'defense':{
  'Defensive Activity':{'weight':.35,'statistics':{'STL_per75':.4,'BLK_per75':.6}},
  'Defensive Activity Rate':{'weight':.25,'statistics':{'STL_pct':.4,'BLK_pct':.6}},
  'WOWY Defensive Impact':{'weight':.40,'statistics':{'WOWY_Defense':1.0}},},
 'impact_value':{
  'WOWY Overall Impact':{'weight':1.0,'statistics':{'WOWY_Net':1.0}},},
 'peak_rules':{
  'regular_season':{'min_games_share':.6,'min_minutes':1400,'required_qualifying_seasons':5,'max_calendar_span':6,'max_skipped_seasons':1,'selection_metric':'average_season_SDI'},
  'playoffs':{'single_season_min_games':3,'five_year_total_min_games':35,'required_appearances':5,'selection_metric':'average_appearance_SDI'}},
 'top_level_category_weights':TOP,'top_level_category_total_weight':1.0}

# Save canonical source inside site so runtime/builds do not depend on /mnt/data.
SITE_WOWY.parent.mkdir(parents=True,exist_ok=True)
pd.read_csv(WOWY_SRC).to_csv(SITE_WOWY,index=False)

pct=pd.read_csv(PCT,low_memory=False)
base=pd.read_csv(BASE,low_memory=False)
w=pd.read_csv(WOWY_SRC,low_memory=False)

# Qualifying regular-season population: use the project's existing PER-75
# qualification output. This preserves the canonical 60% games + 1,400 MP gate
# without creating a second qualification implementation.
qmerge=pd.read_csv('/mnt/data/WOWY_CANONICAL_PER75_MERGE_V1.csv',low_memory=False)
qkeys=qmerge[qmerge["PER75_Qualified"]==True][["Player","Season"]].drop_duplicates()
base["Player"]=base["Player"].astype(str).str.strip()
base["SeasonEndYear"]=pd.to_numeric(base["SeasonEndYear"],errors="coerce")
base["Season"]=base["SeasonEndYear"].map(lambda y: f"{int(y)-1}-{str(int(y))[-2:]}" if pd.notna(y) else "")
q=base[["Player_ID","Player","SeasonEndYear","Season","G","MP"]].merge(qkeys,on=["Player","Season"],how="inner")
q=q.drop_duplicates(["Player_ID","Season"],keep="first")

# Keep only the canonical seasonal percentile rows needed by the formula.
needed=[]
for g in SPEC.values():
 if not isinstance(g,dict): continue
 for gs in g.values():
  if isinstance(gs,dict): needed += list((gs.get('statistics') or {}).keys())
needed=set(needed)-{'WOWY_Offense','WOWY_Defense','WOWY_Net'}
pct['Statistic']=pct['Statistic'].astype(str).str.strip()
p=pct[pct['Statistic'].isin(needed)][['Player_ID','Player','Season','Statistic','Season_Percentile']].copy()
p['Season_Percentile']=pd.to_numeric(p['Season_Percentile'],errors='coerce')
p=p.dropna(subset=['Season_Percentile'])
# One row per player-season-stat.
p=p.drop_duplicates(['Player_ID','Season','Statistic'],keep='first')
wide=p.pivot_table(index=['Player_ID','Player','Season'],columns='Statistic',values='Season_Percentile',aggfunc='first').reset_index()

w['Player']=w['Player'].astype(str).str.strip(); w['Season']=w['Season'].astype(str).str.strip()
wm=w[['Player','Season','Avg WOWY RAPM_Percentile','Avg WOWY O-RAPM_Percentile','Avg WOWY D-RAPM_Percentile']].copy()
wm=wm.rename(columns={'Avg WOWY RAPM_Percentile':'WOWY_Net','Avg WOWY O-RAPM_Percentile':'WOWY_Offense','Avg WOWY D-RAPM_Percentile':'WOWY_Defense'})
for c in ['WOWY_Net','WOWY_Offense','WOWY_Defense']: wm[c]=pd.to_numeric(wm[c],errors='coerce')
wm=wm.drop_duplicates(['Player','Season'],keep='first')

m=q[['Player_ID','Player','SeasonEndYear','Season','G','MP']].merge(wide,on=['Player_ID','Player','Season'],how='left')
m=m.merge(wm,on=['Player','Season'],how='left')

# Compute group/category scores with evidence-aware weighting, matching the API's
# v5 availability philosophy: missing statistics are not imputed; missing groups
# reduce category evidence coverage.
rows=[]
for _,r in m.iterrows():
    cat_scores={}; cat_cov={}
    for cat,groups in SPEC.items():
        if cat in {'peak_rules','top_level_category_weights','top_level_category_total_weight','version','top_level_category_method'} or not isinstance(groups,dict): continue
        gw=[]; intended=0; observed=0
        for _,gs in groups.items():
            if not isinstance(gs,dict): continue
            weight=float(gs.get('weight',0)); intended+=weight
            vals=[]
            for stat,sw in (gs.get('statistics') or {}).items():
                v=r.get(stat,np.nan)
                if pd.notna(v): vals.append((float(v),float(sw)))
            if not vals: continue
            den=sum(sw for _,sw in vals)
            if den<=0: continue
            score=sum(v*sw for v,sw in vals)/den
            gw.append((score,weight)); observed+=weight
        if gw and intended>0:
            den=sum(x[1] for x in gw)
            cat_scores[cat]=sum(x*w for x,w in gw)/den
            cat_cov[cat]=observed/intended
    den=sum(TOP[k] for k in cat_scores)
    total=sum(cat_scores[k]*TOP[k] for k in cat_scores)/den if den>0 else np.nan
    rows.append({
      'Player_ID':r.Player_ID,'Player':r.Player,'SeasonEndYear':int(r.SeasonEndYear),
      'Season':r.Season,'G':r.G,'MP':r.MP,
      'SDI_v4': total,
      'SDI_v4_WOWY': total,
      'SDI_Category_Coverage': sum(TOP[k]*cat_cov.get(k,0) for k in TOP),
      **{f'SDI_{k}_Coverage':cat_cov.get(k,0.0) for k in TOP},
      **{f'SDI_{k}':cat_scores.get(k,np.nan) for k in TOP},
      'WOWY_Net_Percentile':r.get('WOWY_Net',np.nan),
      'WOWY_Offense_Percentile':r.get('WOWY_Offense',np.nan),
      'WOWY_Defense_Percentile':r.get('WOWY_Defense',np.nan),
    })
out=pd.DataFrame(rows)
out.to_csv(OUT,index=False)
SPEC_OUT.write_text(json.dumps(SPEC,indent=2),encoding='utf-8')

report={
 'version':'SDI_v4_WOWY_build_v1','qualified_population':int(len(q)),
 'rows_with_wowy_net':int(out.WOWY_Net_Percentile.notna().sum()),
 'rows_with_wowy_offense':int(out.WOWY_Offense_Percentile.notna().sum()),
 'rows_with_wowy_defense':int(out.WOWY_Defense_Percentile.notna().sum()),
 'wowy_net_coverage':float(out.WOWY_Net_Percentile.notna().mean()),
 'wowy_offense_coverage':float(out.WOWY_Offense_Percentile.notna().mean()),
 'wowy_defense_coverage':float(out.WOWY_Defense_Percentile.notna().mean()),
 'sdi_mean':float(out.SDI_v4.mean()),'sdi_median':float(out.SDI_v4.median()),
 'top_level_weights':TOP,
 'creation_playmaking_subweights':{'Creation Output':.385,'Ball Security / Creation Cost':.315,'WOWY Offensive Impact':.30},
 'defense_subweights':{'Defensive Activity':.35,'Defensive Activity Rate':.25,'WOWY Defensive Impact':.40},
 'impact_value_subweights':{'WOWY Overall Impact':1.0},
}
(Path(DATA)/'SDI_V4_WOWY_BUILD_REPORT_V1.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
