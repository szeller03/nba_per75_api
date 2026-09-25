"""
NBA PER-75 — Player Profile Data Integrity Validator v3

Validator for the v3 schema-first audit report.
It does not modify source data.
"""

from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report_json")
    args = ap.parse_args()
    data = json.loads(Path(args.report_json).read_text(encoding="utf-8"))

    review = []

    # A v3 review is intentionally not a simplistic pass/fail:
    # duplicate rows are reported for human determination because multi-team
    # and split rows can be legitimate in the underlying master architecture.
    for name, samples in data.get("duplicate_samples", {}).items():
        if samples.get("duplicate_rows", 0):
            review.append(
                f"{name}: {samples['duplicate_rows']} duplicate rows under "
                f"{samples.get('evaluated_key')}; inspect samples in report."
            )

    if data.get("regular_peak_json_structure", {}).get("status") == "not_found":
        review.append("Regular 5-Year Peak JSON was not located.")
    if data.get("playoff_peak_json_structure", {}).get("status") == "not_found":
        review.append("Playoff 5-Year Peak JSON was not located.")

    if data.get("career_qualification", {}).get("status") == "checked":
        q = data["career_qualification"]
        if q.get("rule") != "G >= 400 and MP >= 10000":
            review.append("Career qualification rule mismatch.")

    locked = data.get("locked_rules", {})
    if locked.get("route_a_sdi_is_primary") is not True:
        review.append("Route A primary guard missing.")
    if locked.get("companion_percentile_does_not_replace_sdi") is not True:
        review.append("Companion percentile replacement guard missing.")

    print("=" * 80)
    print("PLAYER PROFILE DATA INTEGRITY VALIDATION v3")
    print("=" * 80)
    if review:
        print("STATUS: REVIEW REQUIRED")
        for x in review:
            print(" -", x)
        print()
        print("This is intentional: v3 surfaces evidence instead of labeling")
        print("multi-row architecture as an automatic production-data failure.")
        raise SystemExit(1)

    print("STATUS: STRUCTURAL CHECKS PASSED")

if __name__ == "__main__":
    main()
