r"""
NBA PER-75 — Player Profile Data Integrity Forensic Validator v4.1
"""
from __future__ import annotations
import argparse,json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("report_json")
    args=ap.parse_args()
    d=json.loads(Path(args.report_json).read_text(encoding="utf-8"))
    issues=[]
    m=d.get("master_forensics",{})
    p=d.get("playoff_sdi_forensics",{})
    if m.get("duplicate_group_count",0):
        issues.append(f"Master: {m['duplicate_group_count']} duplicate identity groups require classification.")
    if p.get("duplicate_group_count",0):
        issues.append(f"Playoff SDI: {p['duplicate_group_count']} duplicate identity groups require classification.")
    for k,v in d.get("peak_methodology_checks",{}).items():
        if v.get("invalid_five_season_count",0) or v.get("invalid_span_count",0) or v.get("invalid_gap_count",0):
            issues.append(f"{k}: peak methodology violations detected.")
    if not d.get("sources",{}).get("regular_peak"):
        issues.append("Regular Peak source missing.")
    if not d.get("sources",{}).get("playoff_peak"):
        issues.append("Playoff Peak source missing.")
    print("="*90)
    print("PLAYER PROFILE DATA INTEGRITY FORENSIC VALIDATION v4")
    print("="*90)
    if issues:
        print("STATUS: REVIEW REQUIRED")
        for x in issues: print(" -",x)
        raise SystemExit(1)
    print("STATUS: STRUCTURAL CHECKS PASSED")
if __name__=="__main__":
    main()
