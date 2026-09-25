from pathlib import Path
import os
import runpy
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
api = Path(__file__).resolve().parent / "nba_per75_local_api_phase4.py"

if not api.exists():
    raise FileNotFoundError(str(api))

os.chdir(str(root))
sys.argv = [str(api)] + sys.argv[2:]
runpy.run_path(str(api), run_name="__main__")
