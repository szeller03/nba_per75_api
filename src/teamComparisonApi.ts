
export type TeamIndexItem = {
  Team: string;
  Team_Key?: string;
  First_Season?: string;
  Last_Season?: string;
  Seasons?: number;
  Logo_ID?: string;
  Logo_File?: string;
  [key: string]: unknown;
};

export type TeamSeason = {
  Team: string;
  Season: string;
  W?: number | null;
  L?: number | null;
  ORtg?: number | null;
  DRtg?: number | null;
  NRtg?: number | null;
  rORTG?: number | null;
  rDRTG?: number | null;
  Pace_Final?: number | null;
  [key: string]: unknown;
};

export type TeamComparisonRow = {
  Statistic: string;
  Aggregation_Method?: string;
  Direction?: 'higher_is_better' | 'lower_is_better' | string;
  Team_A: string;
  Team_A_Seasons?: string;
  Team_A_Value?: number | null;
  Team_B: string;
  Team_B_Seasons?: string;
  Team_B_Value?: number | null;
  Difference_A_minus_B?: number | null;
  Statistical_Advantage?: 'Team A' | 'Team B' | 'Tie' | 'Unavailable' | string;
  [key: string]: unknown;
};

export type TeamComparisonResponse = {
  comparison?: TeamComparisonRow[];
  results?: TeamComparisonRow[];
  data?: TeamComparisonRow[];
  metadata?: unknown;
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

function unwrap<T>(payload: any): T[] {
  if (Array.isArray(payload)) return payload;
  for (const key of ['comparison', 'results', 'data', 'items']) {
    if (Array.isArray(payload?.[key])) return payload[key];
  }
  return [];
}

export async function getTeams(): Promise<TeamIndexItem[]> {
  return unwrap<TeamIndexItem>(await getJson('/api/v1/teams'));
}

export async function getTeamSeasons(team: string): Promise<TeamSeason[]> {
  return unwrap<TeamSeason>(
    await getJson(`/api/v1/teams/${encodeURIComponent(team)}/seasons`)
  );
}

export async function compareTeams(
  teamA: string,
  seasonsA: string[],
  teamB: string,
  seasonsB: string[],
  statistics = ['ORtg', 'DRtg', 'rORTG', 'rDRTG', 'Pace_Final']
): Promise<TeamComparisonRow[]> {
  const params = new URLSearchParams({
    team_a: teamA,
    seasons_a: seasonsA.join(','),
    team_b: teamB,
    seasons_b: seasonsB.join(','),
    statistics: statistics.join(','),
  });
  return unwrap<TeamComparisonRow>(
    await getJson(`/api/v1/compare/teams?${params.toString()}`)
  );
}

export function teamLogoUrl(item?: TeamIndexItem | TeamSeason): string | undefined {
  const raw = item?.Logo_File;
  if (!raw || typeof raw !== 'string') return undefined;
  if (/^https?:\/\//i.test(raw) || raw.startsWith('/')) return raw;
  return `/${raw.replace(/^\\+/, '').replace(/^\/+/, '')}`;
}
