from pathlib import Path
import shutil, subprocess, sys

HERE=Path(__file__).resolve().parent
CACHE=HERE/"cache"/"playoff_peak_v2.json"
candidates=[
    Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website74\local_api\cache\playoff_peak_v2.json"),
    Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website73\local_api\cache\playoff_peak_v2.json"),
    Path(r"C:\Users\szell\OneDrive\Desktop\NBA_Per75\api\player_profile_v1\cache\playoff_peak_v2.json"),
]
if not CACHE.exists():
    found=next((p for p in candidates if p.exists()),None)
    if found:
        CACHE.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(found,CACHE)
        print("Copied existing 322-player playoff peak cache from:")
        print(found)
    else:
        print("No existing playoff peak cache was found.")
        print("Run:")
        print("python build_playoff_peak_cache_v2.py")
        sys.exit(2)

subprocess.run([sys.executable,str(HERE/"repair_playoff_peak_percentiles_v1.py")],check=True)
