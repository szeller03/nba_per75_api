# Website215 — profile and percentile source repair

Repairs based on the Website214 runtime log:
- Adds a complete regular-season player profile CSV generated from the current
  master season source.
- Adds a schema-correct canonical long percentile source containing Season,
  Player, Statistic, Value, Season_Percentile, and Historical_Percentile.
- Makes api_profile fall back safely to the authoritative master source when
  a legacy profile CSV is absent.
- Preserves the authoritative SDI v4 season/career/5-year artifacts.

Verified in-process:
- Career profile for Nikola Jokic returns found=True.
- Regular 5-Year Peak returns 2022-2026 with SDI v4 = 88.53137629334783.
