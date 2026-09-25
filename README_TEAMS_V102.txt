NBA PER-75 Teams v102

Four Factors repair is now LOCAL-SOURCE ONLY.

The previous team analytics builder allowed the BRef Four Factors cache to overwrite offensive eFG% and TOV%. That is disabled. Offensive eFG% and TOV% are reconstructed from the canonical team counting stats: eFG%=(FGM+0.5*3PM)/FGA and TOV%=TOV/(FGA+0.44*FTA+TOV). Opponent values remain separate.

One-time optional repair command from local_api:
python repair_team_four_factors_local_v1.py

This command makes no network requests. Then restart the API so the v20 analytics cache is used.
