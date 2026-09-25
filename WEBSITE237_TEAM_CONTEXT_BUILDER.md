# Website237 — Team Competitive Context Builder V2

The team competitive-context layer now uses:

- Land of Basketball season standings pages for regular-season seed/conference/W-L.
- Basketball-Reference's all-time playoff series history table for playoff round reached/eliminated and champion/Finals status.

Run from the project root:

```bash
python local_api/build_team_competitive_context_v2.py
```

Optional historical range:

```bash
python local_api/build_team_competitive_context_v2.py --start 1952 --end 2026
```

The builder caches source HTML under `local_api/cache/team_competitive_sources_v2/`, retries HTTP 429 responses with exponential backoff, and writes `local_api/cache/team_competitive_context_v2.json` plus a build report.

The local API has been pointed at the V2 cache. It does not fall back to the PER-75 `Rk` field as a seed.
