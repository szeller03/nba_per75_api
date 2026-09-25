# PLAYER PROFILE FIX 50.5 — COMPLETE CAREER SDI AUDIT

This is a read-only audit build. It does **not** overwrite any SDI cache or live Career SDI values.

Run from the project root:

```text
python local_api/audit_career_sdi_v1.py --player "Rudy Gobert"
```

The audit now reconstructs the complete locked SDI v4 Career categories, including career-level WOWY Offense, WOWY Defense, and WOWY Net. Seasonal WOWY values are aggregated using canonical regular-season minutes when the master player-season layer is available. The audit then calculates career-level percentiles and applies the locked category/subcategory weights.

For Defense, the diagnostic now explicitly includes:
- STL/75 percentile
- BLK/75 percentile
- STL% percentile
- BLK% percentile
- WOWY Defense percentile
- reconstructed Defense score
- authoritative precomputed Defense score
- difference and coverage

Creation & Playmaking and Impact & Value receive the corresponding complete WOWY diagnostics as well.

The audit is intentionally read-only. Do not treat the reconstructed score as a replacement for the live value until the complete inputs have been verified.
