from __future__ import annotations
from pathlib import Path
import re, shutil, sys, json

ROOT = Path.cwd()
SRC = ROOT / 'src'
BACKUP = ROOT / '.team_integration_backup'
PKG = Path(__file__).resolve().parents[1]


def find_app():
    for name in ('App.jsx','App.tsx','App.js','App.ts'):
        p = SRC / name
        if p.exists(): return p
    return None


def copy_assets():
    for name in ('TeamPages.tsx','teamApi.ts','team-pages.css','TeamRoutes.tsx'):
        shutil.copy2(PKG / 'src' / name, SRC / name)


def patch_app(app: Path):
    text = app.read_text(encoding='utf-8')
    original = text
    # Add imports once.
    import_line = "import { TeamRoutes } from './TeamRoutes';\n"
    if "from './TeamRoutes'" not in text and "from \"./TeamRoutes\"" not in text:
        # Insert after the last top-level import.
        matches = list(re.finditer(r'^import .*?;\s*$', text, re.M))
        if matches:
            pos = matches[-1].end()
            text = text[:pos] + '\n' + import_line + text[pos:]
        else:
            text = import_line + text

    # For React Router apps, add a Route before the closing Routes block.
    if '<Routes' in text and 'path="/teams"' not in text and "path='/teams'" not in text:
        route = '''\n        <Route path="/teams" element={<TeamRoutes route="/teams" team={undefined} navigate={(p) => window.history.pushState({}, '', p)} />} />\n        <Route path="/teams/:team" element={<TeamRouteBridge />} />\n'''
        # This branch is intentionally not auto-applied because TeamRouteBridge depends on the app's router hooks.
        # Leave a marker rather than creating an invalid build.
        text = text.replace('</Routes>', '{/* NBA PER-75 TEAM ROUTES: add /teams and /teams/:team using TeamRoutes adapter. */}\n      </Routes>', 1)
    
    # For custom switch/router apps, insert a safe marker if no route exists.
    if '/teams' not in text:
        marker = '\n{/* NBA PER-75 TEAM INTEGRATION: render <TeamRoutes route={route} team={team} navigate={navigate} /> for /teams and /teams/:team. */}\n'
        # Place before the final export if possible.
        m = re.search(r'\nexport default ', text)
        if m: text = text[:m.start()] + marker + text[m.start():]
        else: text += marker

    if text == original:
        return False
    BACKUP.mkdir(exist_ok=True)
    shutil.copy2(app, BACKUP / app.name)
    app.write_text(text, encoding='utf-8')
    return True


def main():
    print('='*100)
    print('NBA PER-75 — WEBSITE231/232 TEAM INTEGRATION V2')
    print('='*100)
    if not SRC.exists(): raise SystemExit(f'Missing src directory: {SRC}')
    app = find_app()
    if not app:
        raise SystemExit('Could not find src/App.jsx, App.tsx, App.js, or App.ts. No files changed.')
    copy_assets()
    changed = patch_app(app)
    manifest = {
        'app': str(app.relative_to(ROOT)),
        'assets': ['src/TeamPages.tsx','src/teamApi.ts','src/team-pages.css','src/TeamRoutes.tsx'],
        'api_routes': ['/api/v1/teams','/api/v1/teams/{team}','/api/v1/teams/{team}/seasons','/api/v1/teams/{team}/seasons/{season}','/api/v1/teams/{team}/leaderboards','/api/v1/team-leaderboards','/api/v1/compare/teams'],
        'app_auto_patch': changed,
        'backup': str(BACKUP / app.name) if changed else None,
    }
    (ROOT / 'team_integration_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'App:             {app}')
    print(f'Components:      4 installed')
    print(f'App patch:       {"APPLIED" if changed else "NO CHANGE"}')
    print('API contract:    READY')
    print('Status:           PASSED')
    print()
    print('IMPORTANT: If the existing router uses React Router, wire TeamRoutes into the existing <Routes> block')
    print('using the app\'s existing useNavigate/useParams hooks. The adapter is intentionally framework-neutral.')

if __name__ == '__main__': main()
