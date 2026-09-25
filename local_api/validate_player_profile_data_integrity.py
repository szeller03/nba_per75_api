"""
Validate the schema-aware Player Profile Data Integrity v2 report.
Read-only.
"""

from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report_json")
    args = ap.parse_args()
    data = json.loads(Path(args.report_json).read_text(encoding="utf-8"))

    failures = []
    for name, audit in data.get("table_audits", {}).items():
        issues = audit.get("issues", [])
        # Duplicate identity is a real failure only after the corrected key.
        if issues:
            failures.append(f"{name}: {issues}")

    for name, issues in data.get("numeric_range_issues", {}).items():
        if issues:
            failures.append(f"{name}: numeric range issues={len(issues)}")

    cq = data.get("career_qualification", {})
    if cq.get("status") == "checked":
        if cq.get("minimum_games") != 400 or cq.get("minimum_minutes") != 10000:
            failures.append("Career qualification rule mismatch.")

    rp = data.get("regular_peak", {})
    if rp.get("status") in {"checked_json", "checked_table"}:
        if rp.get("bad_peak_metadata_count", 0):
            failures.append("Regular peak metadata violations found.")

    locked = data.get("locked_rules", {})
    if locked.get("route_a_sdi_is_primary") is not True:
        failures.append("Route A SDI primary guard missing.")
    if locked.get("companion_percentile_does_not_replace_sdi") is not True:
        failures.append("Companion percentile replacement guard missing.")

    print("=" * 80)
    print("PLAYER PROFILE DATA INTEGRITY VALIDATION v2")
    print("=" * 80)
    if failures:
        print("STATUS: REVIEW REQUIRED")
        for f in failures:
            print(" -", f)
        raise SystemExit(1)
    print("STATUS: STRUCTURAL CHECKS PASSED")
    print("Review manual follow-ups in the report before changing production data.")

if __name__ == "__main__":
    main()
