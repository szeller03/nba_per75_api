export type TeamIndexItem = {
  Team: string;
  Team_Key?: string;
  First_Season?: string;
  Last_Season?: string;
  Seasons?: number;
  Logo_ID?: string;
  Logo_File?: string;
  Logo_Source?: string;
  [key: string]: unknown;
};

export type TeamSeason = {
  Season: string;
  Team: string;
  Season_Type?: string;
  W?: number | null;
  L?: number | null;
  Win_Pct?: number | null;
  Seed?: number | null;
  Made_Playoffs?: boolean | null;
  Playoff_Finish?: string | null;
  Playoff_Round?: string | null;
  Champion?: boolean | null;
  ORtg?: number | null;
  DRtg?: number | null;
  NRtg?: number | null;
  rORTG?: number | null;
  rDRTG?: number | null;
  Relative_ORtg?: number | null;
  Relative_DRtg?: number | null;
  Relative_NRtg?: number | null;
  Pace_Final?: number | null;
  Logo_ID?: string;
  Logo_File?: string;
  [key: string]: unknown;
};

export type TeamProfile = {
  Team: string;
  team?: TeamIndexItem;
  identity?: TeamIndexItem;
  available_seasons?: string[];
  seasons?: string[];
  [key: string]: unknown;
};

const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL || '';

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error(`API ${response.status}: ${response.statusText}`);
  return response.json() as Promise<T>;
}

function unwrapRecords<T>(payload: any): T[] {
  if (Array.isArray(payload)) return payload;
  for (const key of ['data', 'items', 'teams', 'seasons', 'leaderboards', 'results']) {
    if (Array.isArray(payload?.[key])) return payload[key];
  }
  return [];
}

export async function getTeams(): Promise<TeamIndexItem[]> {
  return unwrapRecords<TeamIndexItem>(await getJson('/api/v1/teams'));
}

export async function getTeam(team: string): Promise<TeamProfile> {
  return getJson<TeamProfile>(`/api/v1/teams/${encodeURIComponent(team)}`);
}

export async function getTeamSeasons(team: string): Promise<TeamSeason[]> {
  return unwrapRecords<TeamSeason>(await getJson(`/api/v1/teams/${encodeURIComponent(team)}/seasons`));
}

export async function getTeamSeason(team: string, season: string): Promise<TeamSeason> {
  return getJson<TeamSeason>(`/api/v1/teams/${encodeURIComponent(team)}/seasons/${encodeURIComponent(season)}`);
}

export async function getTeamLeaderboards(team: string): Promise<Record<string, unknown>[]> {
  return unwrapRecords<Record<string, unknown>>(await getJson(`/api/v1/teams/${encodeURIComponent(team)}/leaderboards`));
}

export async function getTeamLeaderboardFeed(): Promise<Record<string, unknown>[]> {
  return unwrapRecords<Record<string, unknown>>(await getJson('/api/v1/team-leaderboards'));
}

export async function getTeamStatistics(): Promise<Record<string, unknown>[]> {
  return unwrapRecords<Record<string, unknown>>(await getJson('/api/v1/team-statistics'));
}

export function teamLogoUrl(item: TeamIndexItem | TeamSeason | undefined): string | undefined {
  const raw = item?.Logo_File;
  if (!raw || typeof raw !== 'string') return undefined;
  if (/^https?:\/\//i.test(raw) || raw.startsWith('/')) return raw;
  return `/${raw.replace(/^\\+/, '').replace(/^\/+/, '')}`;
}
