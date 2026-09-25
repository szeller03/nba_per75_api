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

const HISTORICAL_TEAM_ABBREVIATIONS: Record<string, string> = {
  'atlanta hawks':'ATL','st. louis hawks':'STL','milwaukee hawks':'MLH','fort wayne pistons':'FTW','detroit pistons':'DET',
  'minneapolis lakers':'MNL','los angeles lakers':'LAL','rochester royals':'ROC','cincinnati royals':'CIN','kansas city-omaha kings':'KCK','kansas city kings':'KCK','sacramento kings':'SAC',
  'syracuse nationals':'SYR','philadelphia warriors':'PHW','san francisco warriors':'SFW','golden state warriors':'GSW',
  'new york knicks':'NYK','boston celtics':'BOS','chicago bulls':'CHI','chicago stags':'CHS','cleveland cavaliers':'CLE','cleveland rebels':'CLR',
  'indiana pacers':'IND','indianapolis olympians':'INO','washington bullets':'WSB','baltimore bullets':'BAL','capital bullets':'CAP','washington wizards':'WAS',
  'seattle supersonics':'SEA','oklahoma city thunder':'OKC','portland trail blazers':'POR','utah jazz':'UTA','new orleans jazz':'NOJ','new orleans pelicans':'NOP',
  'vancouver grizzlies':'VAN','memphis grizzlies':'MEM','charlotte hornets':'CHA','charlotte bobcats':'CHA','brooklyn nets':'BKN','new jersey nets':'NJN','buffalo braves':'BUF',
  'san diego clippers':'SDC','los angeles clippers':'LAC','phoenix suns':'PHX','milwaukee bucks':'MIL','denver nuggets':'DEN','houston rockets':'HOU','san antonio spurs':'SAS','dallas mavericks':'DAL',
  'orlando magic':'ORL','miami heat':'MIA','minnesota timberwolves':'MIN','toronto raptors':'TOR','washington capitols':'WSC','anderson packers':'AND','sheboygan red skins':'SHE','waterloo hawks':'WAT','tri-cities blackhawks':'TCB',
  'providence steamrollers':'PRO','indianapolis jets':'IND','st. louis bombs':'STB','detroit falcons':'DEF','pittsburgh ironmen':'PIT','toronto huskies':'HUS'
};

function seasonEndYear(item: TeamIndexItem | TeamSeason | undefined): number | null {
  const explicit = Number((item as any)?.SeasonEndYear);
  if (Number.isFinite(explicit) && explicit > 1900) return explicit;
  const text = String((item as any)?.Season ?? (item as any)?.season ?? '');
  const m = text.match(/^(\d{4})-(\d{2,4})/);
  if (m) return Number(m[1]) + (m[2].length === 2 ? 1 : 0);
  return null;
}

export function teamLogoCandidates(item: TeamIndexItem | TeamSeason | undefined): string[] {
  if (!item) return [];
  const raw = item?.Logo_File;
  const direct = typeof raw === 'string' && raw
    ? (/^https?:\/\//i.test(raw) || raw.startsWith('/') ? raw : `/${raw.replace(/^\\+/, '').replace(/^\/+/, '')}`)
    : '';
  const team = String((item as any)?.Team ?? (item as any)?.team ?? '').replace(/\*$/,'').trim().toLowerCase();
  const abbr = HISTORICAL_TEAM_ABBREVIATIONS[team];
  const year = seasonEndYear(item);
  const historical = abbr && year ? `https://raw.githubusercontent.com/TGOlson/nba-logos/main/data/img/team/${abbr}_${year}.png` : '';
  const nbaIds: Record<string,string> = {ATL:'1610612737',BOS:'1610612738',BKN:'1610612751',CHA:'1610612766',CHI:'1610612741',CLE:'1610612739',DAL:'1610612742',DEN:'1610612743',DET:'1610612765',GSW:'1610612744',HOU:'1610612745',IND:'1610612754',LAC:'1610612746',LAL:'1610612747',MEM:'1610612763',MIA:'1610612748',MIL:'1610612749',MIN:'1610612750',NOP:'1610612740',NYK:'1610612752',OKC:'1610612760',ORL:'1610612753',PHI:'1610612755',PHX:'1610612756',POR:'1610612757',SAC:'1610612758',SAS:'1610612759',TOR:'1610612761',UTA:'1610612762',WAS:'1610612764'};
  const current = abbr && nbaIds[abbr] ? `https://cdn.nba.com/logos/nba/${nbaIds[abbr]}/primary/L/logo.svg` : '';
  const preferCurrent = Number.isFinite(year) && (year as number) >= 2020;
  return [...new Set((preferCurrent ? [current, direct, historical] : [historical, direct, current]).filter(Boolean))];
}

export function teamLogoUrl(item: TeamIndexItem | TeamSeason | undefined): string | undefined {
  return teamLogoCandidates(item)[0];
}
