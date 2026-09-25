from pathlib import Path
import json, re, unicodedata

ROOT=Path(__file__).resolve().parents[1]
p=ROOT/"data"/"precomputed_5_year_peak"/"regular_profile_peaks.json"
payload=json.loads(p.read_text(encoding="utf-8"))

def norm(v):
    text=unicodedata.normalize("NFKD",str(v or "").replace("*",""))
    text="".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+"," ",text.casefold()).strip()

matches=[x for x in payload["players"] if norm(x.get("player_name"))==norm("Nikola Jokic")]
assert matches, "Nikola Jokic is missing from regular peak cache"
assert matches[0]["peak_start_year"]==2022
assert matches[0]["peak_end_year"]==2026
print("PASS: Nikola Jokic -> 2022-2026")
