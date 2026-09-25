from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
PACKAGE = Path(__file__).resolve().parents[1]
BACKUP = ROOT / ".team_comparison_ui_backup"

FILES = [
    "TeamComparisonPage.tsx",
    "TeamComparisonRoute.tsx",
    "teamComparisonApi.ts",
    "team-comparison.css",
]

def main():
    if not SRC.exists():
        raise FileNotFoundError(f"React src directory not found: {SRC}")
    BACKUP.mkdir(exist_ok=True)
    for name in FILES:
        target = SRC / name
        if target.exists():
            shutil.copy2(target, BACKUP / name)
        shutil.copy2(PACKAGE / name, target)
        print(f"Installed: {name}")
    print(f"Backup: {BACKUP}")
    print("STATUS: PASSED")

if __name__ == "__main__":
    main()
