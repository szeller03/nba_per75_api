# NBA PER-75 — Website231/232 Team Integration V2

This package is the production integration layer for the Team system built on the canonical Team Profile API V1 and Team Comparison API V1.

## What is included

- `src/TeamPages.tsx` — Teams overview + Team Profile UI
- `src/teamApi.ts` — API client
- `src/team-pages.css` — Team visual layer
- `src/TeamRoutes.tsx` — route adapter for the existing application shell
- `tools/apply_team_integration.py` — safe installer with App backup

## Install

From the root of your existing Website231/232 React project:

```bat
py path\to\apply_team_integration.py
```

The installer copies the four integration files into `src/` and creates `.team_integration_backup/` before modifying `App.*`.

## Existing application shell is preserved

Do not replace the existing `App.*`, header, global navigation, player pages, Big Board, Compare, Explorer, or other production routes.

The team integration is additive. The Team pages consume the API rather than CSV files directly.

## Routes

- `/teams`
- `/teams/:team`
- Team comparison endpoint: `/api/v1/compare/teams`

If your existing app uses React Router, use its existing `useNavigate` and `useParams` hooks to pass navigation into `TeamRoutes` rather than introducing a second router.

## Required API process

Keep the existing local API running at `http://127.0.0.1:8000`.

## Visual intent

The Team UI follows Design Prototype v13: editorial cream surface, burgundy controls, compact analytical tables, historical team logos, and success/championship context.
