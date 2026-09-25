# SDI v5 — Availability-Aware Historical Evidence

## Purpose
SDI v5 keeps the locked SDI v4 top-level weights:
- Scoring Volume: 20.0%
- Scoring Efficiency: 18.0%
- Creation / Playmaking: 18.0%
- Rebounding: 10.5%
- Defense: 20.0%
- Impact / Value: 13.5%

Internal subgroup and statistic weights are unchanged.

## Missing-data policy
Missing statistics are **not** assigned a 50th-percentile value.

For each statistic subgroup:
1. Use only statistics actually recorded for that player-season.
2. Preserve the intended relative weights of those available statistics.
3. Renormalize over the available statistic weights.

For each category:
1. Use the available subgroup scores.
2. Preserve intended subgroup weights.
3. Renormalize over available subgroup weights.

For the six top-level categories:
1. Use categories with statistical evidence.
2. Preserve the locked category weights.
3. Renormalize over the available category weights.

Thus missing historical data is not interpreted as average performance, and a
single surviving statistic is not assigned unrelated missing category weights.

## Coverage
Coverage is recorded separately for transparency:
- category coverage is the fraction of intended subgroup weight represented;
- top-level coverage is the fraction of intended category weight represented.

Coverage is metadata only. It does not pull a player's performance score toward
50th percentile.

## Artifacts
Season and career SDI files remain in `data/precomputed_sdi_v4/` for compatibility,
but now contain the SDI v5 availability-aware calculation.
5-Year Peak artifacts are versioned v8 and are used by the API.

## Identity
Website226's canonical duplicate-player identity fix is retained in this build.
The stable website identity registry remains authoritative for profile routing.
