# V8 — Explicit Domain-Separated Spider Architecture

The player spider system is now explicitly separated into three modes:

1. Dominance — exactly six categories:
   - Scoring Volume
   - Scoring Efficiency
   - Creation & Playmaking
   - Rebounding
   - Defense
   - Impact & Value

2. Context — exactly three categories:
   - Offensive Role / Usage
   - Shot Profile
   - Availability / Foul Context

3. All 46 Stats — customizable individual statistics, including the Context statistics.

The Context categories are not silently dropped; they are intentionally excluded from the Dominance spider because the validated taxonomy defines Context as separate from Dominance. The Context spider exposes those three categories directly.

This preserves the statistical architecture and avoids contaminating the Dominance Index with descriptive/context variables.
