# NBA PER-75 — Fix 50.7.4
## Career Percentile Calculation Audit Repair

This package is AUDIT ONLY. It does not modify the Career SDI CSV.

### Problem fixed
The prior Gobert audit ranked the target value correctly in the full population, but then accidentally re-ranked the matching value subset by itself. For any unique value, that subset has rank 1, incorrectly producing a 100th-percentile result.

### Correct method
The audit now:
1. Builds the complete qualified career population.
2. Computes ranks across the COMPLETE population.
3. Locates Gobert's rank inside that full rank vector.
4. Converts that rank to percentile.
5. Independently reports players at or better than Gobert.
6. Reconstructs the defensive SDI from those verified percentiles.

No production CSV is written or changed by this audit.

### Run
From Website241 root:

    python local_api\audit_gobert_career_defense_inputs.py

Output:

    data\GOBERT_CAREER_DEFENSE_INPUT_AUDIT.json
