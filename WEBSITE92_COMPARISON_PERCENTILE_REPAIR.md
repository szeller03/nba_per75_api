# NBA PER-75 Website92 — Comparison Percentile Repair

Website91 still left percentile cells blank. The repair was narrowed to two
likely failure modes:

1. The API did not deterministically select the exact canonical
   `player_percentile_lookup_v1.csv`.
2. The finalized percentile population may expose Era/Historical percentile
   families without a `Season_Percentile_*` family. The comparison default
   previously returned null when its preferred family was absent.

Website92:
- Discovers `player_percentile_lookup_v1.csv` by exact filename from the
  established NBA_Per75 root.
- Gives that file highest priority for regular-season comparisons.
- Falls back to finalized percentile Big Board sources.
- Matches player ID, then cleaned public player name.
- Maps seasons through the common season-end-year parser.
- For `Season` context, uses Season percentile when present, then Era,
  Historical, and generic percentile columns as fallback.
- Supports `Stat_Percentile` naming.
- Adds explicit diagnostics for the selected source and percentile families.

No player statistics, range weighting, SDI, peak calculations, or visual
components were modified.
