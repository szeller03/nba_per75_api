import subprocess, pathlib, sys
root=pathlib.Path(__file__).resolve().parents[1]
p=subprocess.run(["npm","run","build"],cwd=root,text=True,capture_output=True)
print(p.stdout)
print(p.stderr)
sys.exit(p.returncode)
