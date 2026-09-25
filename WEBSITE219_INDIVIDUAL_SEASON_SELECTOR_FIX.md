# Website219 — Individual Season Selector Restoration

Website218 correctly returned the player's individual season universe from the API, but the profile selector depended directly on the generic `seasons` payload. Website219 exposes an explicit `individual_seasons` field and makes the profile selector consume that canonical list, while retaining Career and 5-Year Peak as separate fixed options.

Verified against Nikola Jokic: 2015-16 through 2025-26 are returned as individual season options, alongside Career and 5-Year Peak.
