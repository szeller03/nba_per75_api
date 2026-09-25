from pathlib import Path
import py_compile

ROOT=Path(__file__).resolve().parents[1]
API=ROOT/"local_api"/"nba_per75_local_api.py"
APP=ROOT/"src"/"App.jsx"

py_compile.compile(str(API),doraise=True)
a=APP.read_text(encoding="utf-8")
s=API.read_text(encoding="utf-8")
checks={
 "authoritative playoff per75 precedence": "load_authoritative_playoff_master" in s and "PLAYOFF_PER75_STATS" in s,
 "playoff career possession aggregation": "__poss" in s and "load_playoff_46_career" in s,
 "regular career board": "_regular_career_big_board" in s,
 "encoded player route decoding": "unquote(m.group(1))" in s,
 "live player search": "searchPlayers(query)" in a,
 "clickable player profile": "to={`/players/${encodeURIComponent(player.player_id || player.player_name)}`}" in a,
}
for k,v in checks.items(): print(f"{k}: {'PASS' if v else 'FAIL'}")
if not all(checks.values()): raise SystemExit(1)
print("V42 static integration checks: PASSED")
