# Team Competitive Context Builder V7

Fixes the V6 bootstrap bug where V6 executed V5 with `exec()` but did not provide `__file__`, causing `NameError: __file__ is not defined`.

V7 supplies the real V5 script path to the embedded parser namespace. No network behavior is changed.

Run from the website root:

    python local_api/build_team_competitive_context_v6.py

The builder automatically discovers `land_standings_bundle.json` and `series.html` in the project. Optional explicit paths remain supported:

    python local_api/build_team_competitive_context_v6.py --land-bundle "..." --bref-html "..."
