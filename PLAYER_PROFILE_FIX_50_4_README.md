PLAYER PROFILE FIX 50.4 — CAREER SDI AUDIT

This build adds a read-only Career SDI audit tool. It does not overwrite the SDI cache.

Run from the project root:
  python local_api/audit_career_sdi_v1.py --player "Rudy Gobert"

The audit reconstructs career percentiles from career-level underlying values, applies the locked SDI v4 WOWY weights, and compares the reconstructed six category axes against the precomputed Career SDI axes used by the Profile.

The purpose is to determine whether a Career Defense value such as Gobert's 77 is mathematically consistent with the canonical career inputs, rather than changing the value by hand.
