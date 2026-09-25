# Player Profile Fix 50.7.2 — Gobert Career Defense Input Audit

This is an **audit-only** diagnostic. It does not modify the Career SDI CSV.

It answers why Rudy Gobert's Career Defense score is 73.91 by reporting the exact underlying values, career percentiles, population/rank, and the 35% / 25% / 40% defensive calculation.

Run from the Website241 root:

```powershell
python local_api\audit_gobert_career_defense_inputs.py
```

Output:

`data/GOBERT_CAREER_DEFENSE_INPUT_AUDIT.json`

The audit uses the same canonical Career table and the same Career WOWY reconstruction used by the validated 50.7.1 rebuild. It does **not** change any data.
