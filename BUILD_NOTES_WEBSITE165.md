# Website165 — profile 500 regression repair after duplicate-ID fix

The duplicate-player search fix is retained. The regression was caused by
re-running the full authoritative master-season identity map whenever a
profile request arrived, even though the Players endpoint already returns a
canonical public ID.

Changes:
- Canonical Player_ID requests now resolve immediately from the identity
  registry without rebuilding the master identity map.
- The authoritative ID map remains active at the Players search boundary, so
  duplicate Michael Jordan rows remain collapsed.
- Added `_profile_data_identity()` to separate the public canonical ID from a
  legacy source ID when an enriched profile table still uses an alias.
- Regular Player Profile, Context, and Spider lookups use the source/data ID
  when necessary while continuing to expose the canonical public ID.
- Career spider lookup uses the same data-ID fallback.
- NEW SDI v4 5-Year Peak code is unchanged.
