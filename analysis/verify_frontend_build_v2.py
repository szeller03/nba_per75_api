from pathlib import Path
import subprocess, sys
root=Path(__file__).resolve().parents[1]
print("Checking:", root)
p=subprocess.run(["npm.cmd","run","build"],cwd=root,text=True)
sys.exit(p.returncode)
