from pathlib import Path
import subprocess,sys
root=Path(__file__).resolve().parents[1]
p=subprocess.run(["npm.cmd","run","build"],cwd=root,text=True,capture_output=True)
print(p.stdout)
print(p.stderr)
sys.exit(p.returncode)
