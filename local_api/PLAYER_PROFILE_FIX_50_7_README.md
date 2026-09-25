# Player Profile Fix 50.7 — Canonical Career SDI Rebuild

This build corrects the Career SDI rebuild so the production builder uses the same complete career WOWY reconstruction as the validated Career SDI audit.

## What changed

- Imports and uses `build_career_wowy` from `audit_career_sdi_v2.py` so audit and production use the same canonical WOWY aggregation.
- Career WOWY Offense, WOWY Defense, and WOWY Net are included before Career percentile generation.
- Impact & Value therefore uses the canonical Career WOWY Net percentile instead of becoming null.
- Defense includes the WOWY Defense component at the locked 40% Defense subweight.
- Creation & Playmaking includes WOWY Offense at the locked 30% subweight.
- TRB% alias/derivation logic from the prior repair is preserved.
- Locked top-level SDI weights remain unchanged.
- Adds a hard pre-write validation for Rudy Gobert: all three career WOWY values must be present and Career Impact & Value must be non-null.
- If that validation fails, the live Career SDI CSV is NOT overwritten.

## Run

From the project root:

```powershell
python local_api/build_career_sdi_v4_wowy_v2.py
```

After the rebuild completes successfully, restart the local API and inspect Rudy Gobert's Career SDI on Player Profile.

## Important

This build does not alter individual-season SDI, playoff SDI, 5-Year Peak SDI, Big Board, Explorer, Compare, or Profile request orchestration.
