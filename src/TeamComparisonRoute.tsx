
import React from 'react';
import { TeamComparisonPage } from './TeamComparisonPage';

export function TeamComparisonRoute({
  route,
}: {
  route: string;
}) {
  if (route === '/compare/teams') return <TeamComparisonPage />;
  return null;
}
