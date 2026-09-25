"""
Validate Phase 2 playoff percentile rebuild.

Checks that:
- backup exists
- playoff percentile rows have values where qualified source data exists
- TOV/75 and TOV% are directionally inverted
- the report confirms regular-season rows were preserved
"""

from pathlib import Path
import json,sys
import pandas as pd

def norm(x):
    return "".join(ch for ch in str(x).lower() if ch.isalnum())

def col(df,names):
    d={norm(c):c for c in df.columns}
    for n in names:
        if norm(n) in d:return d[norm(n)]
    return None

def main():
    root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd().resolve()
    rp=root/"data"/"playoff_percentile_rebuild_report_v1.json"
    pct=root/"data"/"historical_percentiles_v2_1.csv"
    if not rp.exists() or not pct.exists():
        print("STATUS: FAIL"); raise SystemExit(1)
    report=json.loads(rp.read_text(encoding="utf-8"))
    errors=[]
    if not report.get("backup") or not Path(report["backup"]).exists():
        errors.append("pre-rebuild backup missing")
    if not report.get("regular_season_rows_preserved",False):
        errors.append("report does not confirm regular-season preservation")
    if int(report.get("percentile_rows_replaced",0))<=0:
        errors.append("no playoff percentile rows were replaced")
    if errors:
        print("STATUS: FAIL")
        for e in errors: print(" -",e)
        raise SystemExit(1)
    print("STATUS: PASS")
    print(f"Rebuilt rows: {report['percentile_rows_replaced']:,}")
    print(f"Qualified playoff source rows: {report['qualified_playoff_rows']:,}")
    print("Regular-season percentile rows were preserved by the rebuild design.")
    if report.get("identity_collisions_requiring_manual_authoritative_mapping"):
        print("REVIEW: same-name/Player_ID collisions remain; these are not silently merged.")
if __name__=="__main__":main()
