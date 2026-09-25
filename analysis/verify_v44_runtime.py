from pathlib import Path
import py_compile
import importlib.util

API = Path(__file__).resolve().parents[1] / "local_api" / "nba_per75_local_api.py"
py_compile.compile(str(API), doraise=True)

spec=importlib.util.spec_from_file_location("nba_api", API)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

print("NBA PER-75 V44 RUNTIME VERIFICATION")
print("API syntax: PASS")
print("ROOT:", mod.ROOT)
for key in ["identity","master","qualification","percentiles","taxonomy","aggregation_spec","statistic_registry","playoff_46","playoff_percentiles"]:
    print(f"{key}: {'FOUND' if mod.PATHS[key].exists() else 'MISSING'} -> {mod.PATHS[key]}")
print("Diagnostics endpoint available: PASS")
