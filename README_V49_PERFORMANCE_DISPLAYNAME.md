# NBA PER-75 Website V49 — Performance & Display Name Repair

- Removed all `*` markers from public-facing player names without modifying canonical source data.
- Applied cleaned names to player search, Big Board, player profiles, and spider-chart titles.
- Cached Era Average population aggregation by dataset + era.
- Cached Era Average percentile populations by dataset + era + statistic.
- Preserved V48 career qualification and Era Average methodology.
- Statistical Dominance Index remains intentionally unchanged.

Era Average thresholds:
- Regular Season: >=40% participation, >=250 games, >=6,000 minutes.
- Playoffs: >=40% participation, >=40 games, >=1,250 minutes.
