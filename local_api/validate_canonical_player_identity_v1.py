"""
Validate Phase 1 canonical identity outputs.

Usage:
    python local_api/validate_canonical_player_identity_v1.py "C:\\path\\to\\NBA_Per75_Website241"
"""

from pathlib import Path
import json
import sys
import pandas as pd


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    out = root / "data" / "player_identity"

    canonical_path = out / "canonical_player_identity_v1.csv"
    collisions_path = out / "player_id_collision_groups_v1.csv"
    report_path = out / "identity_repair_report_v1.json"

    missing = [str(p) for p in [canonical_path, collisions_path, report_path] if not p.exists()]
    if missing:
        print("STATUS: FAIL")
        print("Missing outputs:")
        for p in missing:
            print(" -", p)
        raise SystemExit(1)

    canonical = pd.read_csv(canonical_path, low_memory=False)
    collisions = pd.read_csv(collisions_path, low_memory=False)
    report = json.loads(report_path.read_text(encoding="utf-8"))

    errors = []
    if canonical.empty:
        errors.append("canonical identity file is empty")
    if "Canonical_Player_ID" not in canonical.columns:
        errors.append("Canonical_Player_ID missing")
    if "Season_Type" not in canonical.columns:
        errors.append("Season_Type missing")
    if "Identity_Status" not in canonical.columns:
        errors.append("Identity_Status missing")

    # The repair layer must never silently remove source rows.
    if len(canonical) != int(report.get("rows", -1)):
        errors.append(
            f"row preservation mismatch: canonical={len(canonical)} master={report.get('rows')}"
        )

    if errors:
        print("STATUS: FAIL")
        for e in errors:
            print(" -", e)
        raise SystemExit(1)

    print("STATUS: PASS")
    print(f"Canonical rows: {len(canonical):,}")
    print(f"Ambiguous candidate rows: {(canonical['Identity_Status'] != 'CANONICAL').sum():,}")
    print(f"Collision rows: {len(collisions):,}")
    print()
    print("No production files were modified by this validation.")


if __name__ == "__main__":
    main()
