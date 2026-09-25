FIX57 — Canonical Profile SDI Axis Repair

This patch addresses the repeated Profile SDI routing problem rather than adding another isolated cache override.

Changes:
- Regular-season Career Profile category axes bypass the legacy frozen Career SDI axis file and use the active canonical formula path.
- Career Creation percentile is ranked from the corrected canonical season SDI layer against the qualified Career population.
- Playoff season/category axes now always receive a companion percentile; if the raw playoff SDI index is unavailable, a cached population fallback is used instead of returning blank Profile dimensions.
- Playoff Career uses the same fallback population logic.
- Playoff 5-Year Peak category axes are derived from the canonical playoff season SDI index and the one-peak-per-player population when available, with a safe percentile fallback.
- Profile UI is strictly percentile-only. Raw SDI remains in the underlying API/data and Big Board.

No headshots or canonical raw statistic values are modified by this patch.
