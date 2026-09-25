# NBA PER-75 Website106 — Precomputed Team Index

The Team page no longer builds its team database by reading the full player
master CSV during a page request.

Run once from the Website106 root:

    python local_api\precompute_team_index_v1.py

The script creates:
- local_api/cache/team_index_v1.json
- local_api/cache/team_rosters_v1.json

After that, `/api/v1/teams` is a small JSON read and should return essentially
immediately.

Important:
- The current canonical master source represented in this build is player
  regular-season data. Therefore the precompute script populates Regular
  Season team rows.
- Playoffs are deliberately not fabricated. The API returns an empty playoff
  index until a canonical playoff team source is supplied.
- If the cache has not been generated, the Teams page now reports that state
  immediately instead of sitting on an indefinite loading screen.
- Team-season detail uses the compact roster cache when available.
