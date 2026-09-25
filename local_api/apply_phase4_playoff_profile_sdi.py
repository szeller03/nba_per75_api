"""
Apply Phase 4 Player Profile Playoff SDI integration to an existing Website241.

This is a conservative installer. It:
- backs up local_api/nba_per75_local_api.py
- replaces it with the Phase-4 API build
- does not alter frontend files, data, or caches

Usage:
    python local_api/apply_phase4_playoff_profile_sdi.py "C:\\path\\to\\NBA_Per75_Website241"

The package's nba_per75_local_api.py is copied into the target local_api folder.
"""
from pathlib import Path
import shutil, sys

PACKAGE_ROOT=Path(__file__).resolve().parent
TARGET_ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd().resolve()
target=TARGET_ROOT/"local_api"/"nba_per75_local_api.py"
source=PACKAGE_ROOT/"nba_per75_local_api.py"

if not source.exists():
    raise FileNotFoundError(source)
if not target.exists():
    raise FileNotFoundError(f"Target API not found: {target}")

backup=target.with_name("nba_per75_local_api.pre_phase4_playoff_profile_sdi.py")
shutil.copy2(target,backup)
shutil.copy2(source,target)

print("PHASE 4 APPLIED")
print(f"API: {target}")
print(f"Backup: {backup}")
print("Frontend files were not modified.")
