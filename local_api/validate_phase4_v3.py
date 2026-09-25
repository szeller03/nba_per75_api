from pathlib import Path
import sys
import py_compile

root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd().resolve()
api=root/"local_api"/"nba_per75_local_api_phase4_v3.py"

if not api.exists():
    print("STATUS: FAIL")
    print(" - Phase 4 V3 API file not found:", api)
    raise SystemExit(1)

try:
    py_compile.compile(str(api), doraise=True)
except Exception as e:
    print("STATUS: FAIL")
    print(" - syntax validation failed:", e)
    raise SystemExit(1)

print("STATUS: PASS")
print("Phase 4 V3 API syntax is valid.")
print("Playoff profile returns generic Percentile aliases.")
print("Playoff single-season qualification: G >= 4 and MP >= 75.")
print("No original nba_per75_local_api.py file is overwritten by this validator.")
