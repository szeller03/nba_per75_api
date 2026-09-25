"""Validate that the Phase 4 API contains the playoff Profile SDI bridge."""
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd().resolve()
p=root/"local_api"/"nba_per75_local_api.py"
if not p.exists():
    print("STATUS: FAIL\n - nba_per75_local_api.py missing")
    raise SystemExit(1)
t=p.read_text(encoding="utf-8")
required=[
    "_playoff_profile_sdi_payload",
    "_playoff_profile_cache_sdi",
    '"category_axes":_playoff_axes',
    '"SDI_v4_Playoffs"',
    '"playoff_sdi_source"',
]
missing=[x for x in required if x not in t]
if missing:
    print("STATUS: FAIL")
    for x in missing: print(" - missing:",x)
    raise SystemExit(1)
compile(t,str(p),"exec")
print("STATUS: PASS")
print("Phase 4 playoff Profile SDI integration is present and syntactically valid.")
