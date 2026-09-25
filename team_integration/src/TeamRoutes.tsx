import React from 'react';
import { TeamsPage, TeamProfilePage } from './TeamPages';

/**
 * Adapter for the existing Website231/232 application shell.
 * Keep the site's existing global shell/header/navigation intact.
 */
export function TeamRoutes({
  route,
  team,
  navigate,
}: {
  route: string;
  team?: string;
  navigate: (path: string) => void;
}) {
  if (route === '/teams') {
    return <TeamsPage onOpenTeam={(name) => navigate(`/teams/${encodeURIComponent(name)}`)} />;
  }
  if (route.startsWith('/teams/')) {
    const name = team || decodeURIComponent(route.slice('/teams/'.length));
    return <TeamProfilePage team={name} onBack={() => navigate('/teams')} />;
  }
  return null;
}
