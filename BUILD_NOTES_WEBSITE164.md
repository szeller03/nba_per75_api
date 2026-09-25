# Website164 — definitive duplicate Player ID consolidation

The remaining Michael Jordan duplicate was caused by the Players search still
being able to emit multiple source Player_ID rows even after the profile
identity registry had been normalized.

This build adds a final authoritative identity layer:

- Build a Player_ID -> canonical Player_ID map directly from the master
  player-season table.
- Normalize names consistently.
- Compare season histories for same-name IDs.
- IDs with >=3 overlapping seasons, or >=50% overlap of the smaller career,
  are treated as source aliases for the same historical player.
- The ID with the largest authoritative season footprint is selected as the
  canonical ID.
- `/api/v1/players` now deduplicates on that canonical ID before returning
  search results.
- `/api/v1/players/<id>/profile` resolution also maps stale/source IDs to the
  canonical ID, so an old duplicate ID cannot open a second public profile.
- The existing NEW SDI v4 5-Year Peak implementation from Website163 is
  untouched.
