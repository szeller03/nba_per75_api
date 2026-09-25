# Website216 — Context Profile Taxonomy Repair

Website215 successfully fixed profile loading and canonical percentiles, but the
runtime showed a separate 500 on `/context` because
`player_statistic_taxonomy_v1/player_statistic_taxonomy_v1.csv` was absent.

This build adds the required taxonomy source with the Context-domain categories
used by `api_context_profile`:
- Offensive Role / Usage
- Shot Profile
- Availability / Foul Context

Verified:
- API syntax/import passes.
- Nikola Jokic Career context endpoint returns successfully.
- Nikola Jokic 5-Year Peak context endpoint returns successfully.
- Regular 5-Year Peak remains 2021-22 through 2025-26 with SDI v4 = 88.53137629334783.
