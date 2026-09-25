# SDI v4 corrected subcategory weights

This build synchronizes the regular-season SDI v4 locked JSON and the runtime player_subcategory_aggregation_spec_v1.csv.

Regular-season effective category weights:
- Scoring Volume: PTS/75 45%, FGA/75 35%, FTA/75 20%.
- Scoring Efficiency: Overall Efficiency 60% (rTS 100%); Component Efficiency 40% (2P% 50%, 3P% 40%, FT% 10%).
- Creation / Playmaking: Creation Output 38.5% (AST/75 80%, AST% 20%); Ball Security / Creation Cost 31.5% (AST:TOV 100%, TOV% 0%); WOWY Offense 30%.
- Rebounding: Production 75% (ORB/75 45%, DRB/75 35%, TRB/75 20%); Rate 25% (OREB% 45%, DREB% 35%, TRB% 20%).
- Defense: Activity 35% (STL/75 35%, BLK/75 65%); Rate 25% (STL% 35%, BLK% 65%); WOWY Defense 40%.
- Impact / Value: WOWY Net 100%.

Top-level weights remain 22%, 20%, 20%, 10.5%, 22%, 5.5%.


## Career recalculation fix
Career category axes no longer trust the frozen `regular_career_sdi_v4_wowy_rts.csv` composite when the canonical Career percentile layer is available. The Player Profile rebuilds Career category scores from the current locked aggregation specification, so subcategory changes propagate into Career Creation, Scoring, Efficiency, Rebounding, Defense, and Impact axes. The frozen CSV remains only as a compatibility fallback.
