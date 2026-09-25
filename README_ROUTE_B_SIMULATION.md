# Route B Career SDI Simulation

This is a **diagnostic only**. It does not modify any production website files.

It takes the existing weighted Career SDI category composites and adds a second
percentile layer:

    existing weighted category score
        -> percentile rank across Qualified_Career population

This lets us compare the current display with Route B before deciding whether
the public-facing SDI should be re-percentiled.

## Run

From the website root:

```powershell
python local_api/route_b_career_sdi_simulation.py
```

The script looks for:

`data/regular_career_sdi_v4_wowy_rts.csv`

and several fallback locations.

## Outputs

- `local_api/route_b_career_sdi_comparison.csv`
  - Every qualified player
  - Current composite
  - Route B percentile
  - Route B minus current shift

- `local_api/route_b_career_sdi_top25_by_category.csv`
  - Top 25 under Route B for Scoring, Efficiency, Creation,
    Rebounding, Defense, Impact, and Overall SDI

- `local_api/route_b_career_sdi_named_players.csv`
  - Side-by-side results for notable players including Duncan,
    Hakeem, Russell, Gobert, Rodman, etc.

## Important

The current methodology is untouched. This is only a simulation.
