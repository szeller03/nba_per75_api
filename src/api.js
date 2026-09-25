const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

const API_RETRY_DELAYS = [250, 600, 1200];
const API_CACHE_TTL = 10 * 60 * 1000;
const API_CACHE_MAX = 160;
const responseCache = new Map();
const inFlight = new Map();

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function requestJson(path, options = {}) {
  const { signal } = options;
  const key = path;
  if (!signal) {
    const hit = responseCache.get(key);
    if (hit && Date.now() - hit.time < API_CACHE_TTL) { responseCache.delete(key); responseCache.set(key, hit); return hit.data; }
    if (hit) responseCache.delete(key);
    const pending = inFlight.get(key);
    if (pending) return pending;
  }
  const run = (async()=>{
    let lastError = null;
    for (let attempt = 0; attempt <= API_RETRY_DELAYS.length; attempt++) {
      try {
        const response = await fetch(`${API_BASE}${path}`, { signal });
        if (response.ok) {
          const data = await response.json();
          if (!signal) { responseCache.set(key, {time:Date.now(), data}); while (responseCache.size > API_CACHE_MAX) responseCache.delete(responseCache.keys().next().value); }
          return data;
        }
        if (response.status >= 500 && attempt < API_RETRY_DELAYS.length) { await sleep(API_RETRY_DELAYS[attempt]); continue; }
        throw new Error(`API request failed (${response.status})`);
      } catch (error) {
        lastError = error;
        if (error?.name === "AbortError") throw error;
        if (attempt < API_RETRY_DELAYS.length) { await sleep(API_RETRY_DELAYS[attempt]); continue; }
        throw lastError;
      }
    }
    throw lastError || new Error("API request failed");
  })();
  if (!signal) { inFlight.set(key, run); try { return await run; } finally { if (inFlight.get(key) === run) inFlight.delete(key); } }
  return run;
}

async function get(path) {
  return requestJson(path);
}

async function getWithSignal(path, signal) {
  // Profile reads are safe to share across view transitions. Keep them in the
  // same cache/in-flight pool as normal reads so switching Career/Season/Peak/
  // Playoffs never throws away a response that is already being fetched.
  // Abort is handled at the UI-state layer via request ids; the shared request
  // is allowed to finish and warm the cache for the next view.
  return requestJson(path);
}

export const searchPlayers = (query) =>
  get(`/public/players?q=${encodeURIComponent(query)}`);
export const searchPlayersBatch = (names) =>
  get(`/public/players/curated?names=${names.map(encodeURIComponent).join(",")}`);
export const getPlayerSeasonBundles = (playerId, seasonType = "Regular Season", signal) =>
  signal ? getWithSignal(`/public/players/${encodeURIComponent(playerId)}/season-bundles?season_type=${encodeURIComponent(seasonType)}`, signal) : get(`/public/players/${encodeURIComponent(playerId)}/season-bundles?season_type=${encodeURIComponent(seasonType)}`);

// Profile prefetch: keep navigation-critical requests small and serialize
// heavyweight alternate-context warmups so they do not compete with the
// profile request that is currently rendering. This is performance-only: it
// never changes the source, values, formulas, or percentile layers.
const __profilePrefetch = new Map();
function __prefetchBundle(id, seasonType) {
  const key = `${id}|${seasonType}`;
  if (!__profilePrefetch.has(key)) {
    __profilePrefetch.set(key, getPlayerSeasonBundles(id, seasonType).catch(() => null));
  }
  return __profilePrefetch.get(key);
}
function __prefetchProfile(id, seasonType, season, percentileContext) {
  const key = `${id}|${seasonType}|${season}|${percentileContext}`;
  if (!__profilePrefetch.has(key)) {
    // Route through the same exact-context profile helper used by the visible
    // page. This makes playoff profile prefetch and navigation share the same
    // in-flight promise instead of creating two independent requests.
    __profilePrefetch.set(key, getPlayerProfileBundle(id, seasonType, season, percentileContext).catch(() => null));
  }
  return __profilePrefetch.get(key);
}
export function prefetchPlayerProfile(playerId, mode="full") {
  const id = String(playerId ?? "");
  if (!id) return;

  // Navigation-critical prefetching is context-aware. In particular, hovering
  // the PLAYOFFS control should warm the exact playoff profile + spider rather
  // than starting the much heavier season-bundles request and then making the
  // user compete with that request on click. This is performance-only: all
  // responses still come from the existing canonical endpoints.
  if (mode === "playoffs") {
    // Warm all three navigation-critical playoff payloads together. The season
    // bundle supplies the table + Career aggregate; the exact profile and
    // spider supply the header SDI. requestJson dedupes these with the actual
    // view, so a click during prefetch simply joins the same in-flight work.
    __prefetchBundle(id, "Playoffs");
    __prefetchProfile(id, "Playoffs", "Career", "Career");
    const spiderKey = `${id}|spider|Playoffs|Career|Career`;
    if (!__profilePrefetch.has(spiderKey)) {
      const qs = new URLSearchParams({season:"Career", context:"Career", season_type:"Playoffs"});
      __profilePrefetch.set(spiderKey, get(`/players/${encodeURIComponent(id)}/spider?${qs.toString()}`).catch(() => null));
    }
    return;
  }

  // The regular-season Career view is supplied by the canonical season-bundle
  // layer, so warm that layer for player-card navigation. Also warm the exact
  // Career SDI spider during hover so the initial header does not wait for a
  // second request after navigation.
  __prefetchBundle(id, "Regular Season");
  const careerSpiderKey = `${id}|spider|Regular Season|Career|Career`;
  if (!__profilePrefetch.has(careerSpiderKey)) {
    const qs = new URLSearchParams({season:"Career", context:"Career", season_type:"Regular Season"});
    __profilePrefetch.set(careerSpiderKey, get(`/players/${encodeURIComponent(id)}/spider?${qs.toString()}`).catch(() => null));
  }

  if (mode === "full") {
    // Also warm Playoffs, but do it after the regular bundle is requested so a
    // player-card click does not create two expensive backend jobs at once.
    const key = `${id}|__playoff_bundle_after_regular`;
    if (!__profilePrefetch.has(key)) {
      const run = (async()=>{
        await __prefetchBundle(id, "Regular Season");
        await __prefetchBundle(id, "Playoffs");
      })().catch(()=>null);
      __profilePrefetch.set(key, run);
    }
  }

  if (mode === "peak") {
    const tasks = [__prefetchProfile(id,"Regular Season","5-Year Peak","Peak")];
    const spiderKey = `${id}|spider|Regular Season|Peak`;
    if (!__profilePrefetch.has(spiderKey)) {
      const qs = new URLSearchParams({season:"5-Year Peak",context:"Peak",season_type:"Regular Season"});
      __profilePrefetch.set(spiderKey,get(`/players/${encodeURIComponent(id)}/spider?${qs.toString()}`).catch(()=>null));
    }
    return Promise.all(tasks).catch(()=>null);
  }

  if (mode === "background") {
    const bgKey = `${id}|__background_profile_warm`;
    if (!__profilePrefetch.has(bgKey)) {
      const tasks = [
        __prefetchProfile(id, "Regular Season", "5-Year Peak", "Peak"),
        __prefetchProfile(id, "Playoffs", "5-Year Peak", "Peak"),
      ];
      for (const [st] of [["Regular Season"],["Playoffs"]]) {
        const spiderKey = `${id}|spider|${st}|Peak`;
        if (!__profilePrefetch.has(spiderKey)) {
          const qs = new URLSearchParams({season:"5-Year Peak", context:"Peak", season_type:st});
          __profilePrefetch.set(spiderKey, get(`/players/${encodeURIComponent(id)}/spider?${qs.toString()}`).catch(() => null));
        }
      }
      __profilePrefetch.set(bgKey, Promise.all(tasks).catch(() => null));
    }
  }
}

// Warm an individual-season spider only when the user points at the row.
// requestJson dedupes and caches the response, making the subsequent click
// effectively a cache hit without changing any data.
export function prefetchPlayerSpider(playerId, season, seasonType="Regular Season") {
  const id = String(playerId ?? "");
  const s = String(season ?? "");
  if (!id || !s) return;
  const key = `${id}|spider|${seasonType}|${s}`;
  if (__profilePrefetch.has(key)) return;
  const qs = new URLSearchParams({season:s, context:"Season", season_type:seasonType});
  __profilePrefetch.set(key, get(`/players/${encodeURIComponent(id)}/spider?${qs.toString()}`).catch(() => null));
}

export const getPlayerSeasons = (playerId, seasonType = "Regular Season") =>
  get(`/players/${encodeURIComponent(playerId)}/seasons?season_type=${encodeURIComponent(seasonType)}`);


export const getPlayerProfile = (playerId, season, seasonType = "Regular Season") => {
  const qs = new URLSearchParams();
  if (season) qs.set("season", season);
  if (seasonType) qs.set("season_type", seasonType);
  return get(`/players/${encodeURIComponent(playerId)}/profile?${qs.toString()}`);
};

export const getPlayerSpider = (playerId, season, context, stats = [], seasonType = "Regular Season", signal) => {
  const qs = new URLSearchParams();
  if (season) qs.set("season", season);
  if (context) qs.set("context", context);
  if (stats.length) qs.set("stats", stats.join(","));
  if (seasonType) qs.set("season_type", seasonType);
  return getWithSignal(`/players/${encodeURIComponent(playerId)}/spider?${qs.toString()}`, signal);
};

export const getPlayerContextProfile = (playerId, season, context, seasonType = "Regular Season", signal) => {
  const qs = new URLSearchParams();
  if (season) qs.set("season", season);
  if (context) qs.set("context", context);
  if (seasonType) qs.set("season_type", seasonType);
  return getWithSignal(`/players/${encodeURIComponent(playerId)}/context?${qs.toString()}`, signal);
};

export const getPlayerCategories = (playerId, signal) =>
  getWithSignal(`/players/${encodeURIComponent(playerId)}/categories`, signal);

export const getPlayerSubcategories = (playerId, signal) =>
  getWithSignal(`/players/${encodeURIComponent(playerId)}/subcategories`, signal);

export const getStatisticRegistry = () => get("/statistics");


export async function getBigBoardSeasonOptions(seasonType = "Regular Season") {
  const qs = new URLSearchParams({
    season: "Historical Percentile",
    context: "Historical",
    statistic: "PTS_per75",
    sort: "desc",
    limit: "1",
    offset: "0",
    scope: "single",
    season_type: seasonType,
  });
  return get(`/big-board?${qs.toString()}`);
}

export const getBigBoardCompanion = async (season, context, statistic, playerIds = [], era = "") => {
  const ids = [...new Set((playerIds || []).map(x => String(x || "").trim()).filter(Boolean))].slice(0, 500);
  if (!ids.length) return { rows: [], count: 0, public_layer: true, companion: true };
  const qs = new URLSearchParams();
  if (season) qs.set("season", season);
  if (context) qs.set("context", context);
  if (statistic) qs.set("statistic", statistic);
  if (era) qs.set("era", era);
  qs.set("player_ids", ids.join(","));
  try { const fast = await get(`/public/big-board-companion?${qs.toString()}`); if (fast?.public_layer) return fast; } catch {}
  return { rows: [], count: 0, public_layer: true, companion: true };
};

export const getBigBoard = async (season, context, statistic, sort="desc", search="", limit=100, scope="single", seasonType="Regular Season", era="", companion=false, anchorStatistic="", fetchAll=false) => {
  const customBoardStatistic = !statistic || ["WOWY_Offense","WOWY_Defense","WOWY_Net","Statistical Dominance Index","Statistical Dominance","SDI"].includes(String(statistic));
  if (seasonType === "Regular Season" && !customBoardStatistic && !["career","five_year_peak","5-year peak","peak","era_average","era average"].includes(String(scope||"").toLowerCase())) {
    const qs = new URLSearchParams();
    if (season) qs.set("season", season);
    if (context) qs.set("context", context);
    if (statistic) qs.set("statistic", statistic);
    qs.set("sort", sort); if (search) qs.set("search", search); qs.set("limit", String(limit)); if (era) qs.set("era", era);
    try { const fast = await get(`/public/big-board?${qs.toString()}`); if (fast?.public_layer) return fast; } catch {}
  }
  const makeQuery = (offset, pageLimit=500) => {
    const qs = new URLSearchParams();
    if (season) qs.set("season", season);
    if (context) qs.set("context", context);
    if (statistic) qs.set("statistic", statistic);
    qs.set("sort", sort);
    if (search) qs.set("search", search);
    qs.set("limit", String(pageLimit));
    qs.set("offset", String(offset));
    qs.set("scope", scope);
    if (seasonType) qs.set("season_type", seasonType);
    if (era) qs.set("era", era);
    if (companion) qs.set("companion", "1");
    if (anchorStatistic) qs.set("anchor_statistic", anchorStatistic);
    return qs;
  };

  const first = await get(`/big-board?${makeQuery(0, Math.max(500, limit)).toString()}`);
  if (Array.isArray(first.rows)) {
    // When the bridge returns paginated rows directly, request enough rows
    // for companion-stat joins and then trim only at the UI boundary.
    const total = Number(first.total || first.count || first.rows.length);
    const pageSize = Number(first.limit || Math.max(500, limit));
    const allRows = [...first.rows];
    if (fetchAll && total > allRows.length && pageSize > 0) {
      const offsets=[];
      for(let offset=allRows.length;offset<total;offset+=pageSize) offsets.push(offset);
      for(let i=0;i<offsets.length;i+=5){
        const page=await Promise.all(offsets.slice(i,i+5).map(offset=>get(`/big-board?${makeQuery(offset,pageSize).toString()}`)));
        page.forEach(r=>{if(Array.isArray(r.rows))allRows.push(...r.rows);});
      }
    }
    return {...first,rows:allRows.slice(0,limit)};
  }

  // The current FastAPI bridge exposes the precomputed percentile table as
  // {data,total,offset,limit}. Normalize that source into the shape the
  // existing React Big Board already understands.
  if (!Array.isArray(first.data)) return first;

  const all = [...first.data];
  const total = Number(first.total || all.length);
  const pageSize = Number(first.limit || 500);
  const offsets = [];
  if (fetchAll) for (let offset = all.length; offset < total; offset += pageSize) offsets.push(offset);
  for (let i=0; i<offsets.length; i+=5) {
    const page = await Promise.all(offsets.slice(i,i+5).map(offset =>
      get(`/big-board?${makeQuery(offset, pageSize).toString()}`)
    ));
    page.forEach(r => { if (Array.isArray(r.data)) all.push(...r.data); });
  }

  const normalizeSeason = (v) => String(v || "").trim();
  const eraForSeason = (value) => {
    const m = normalizeSeason(value).match(/^(\d{4})/);
    if (!m) return "";
    const y = Number(m[1]);
    if (y >= 1951 && y <= 1969) return "1951-52_to_1969-70";
    if (y >= 1970 && y <= 1979) return "1970-71_to_1979-80";
    if (y >= 1980 && y <= 1989) return "1980-81_to_1989-90";
    if (y >= 1990 && y <= 1999) return "1990-91_to_1999-00";
    if (y >= 2000 && y <= 2009) return "2000-01_to_2009-10";
    if (y >= 2010 && y <= 2019) return "2010-11_to_2019-20";
    if (y >= 2020) return "2020-21_to_2025-26";
    return "";
  };

  let filtered = all.filter(r => !seasonType || String(r.Season_Type || "Regular Season") === seasonType);
  if (season && season !== "Historical Percentile") filtered = filtered.filter(r => normalizeSeason(r.Season) === normalizeSeason(season));
  if (era) filtered = filtered.filter(r => eraForSeason(r.Season) === era);
  if (search) filtered = filtered.filter(r => String(r.Player || "").toLowerCase().includes(search.toLowerCase()));

  const stat = statistic || "PTS_per75";
  const pctPrefix = context === "Season" ? "Season" : context === "Era" ? "Era" : "Historical";
  const pctKey = `${pctPrefix}_Percentile_${stat}`;
  const valueKey = stat;
  const rows = filtered.map(r => ({
    player_id: r.Player_ID || r.player_id || r.Player_Slug || r.Player,
    player_name: r.Player,
    season: r.Season,
    season_label: r.Season,
    value: r[valueKey] ?? null,
    percentile: r[pctKey] ?? null,
  })).filter(r => r.percentile != null || r.value != null);

  rows.sort((a,b) => {
    const av = Number(a.percentile ?? a.value ?? -Infinity);
    const bv = Number(b.percentile ?? b.value ?? -Infinity);
    return sort === "asc" ? av-bv : bv-av;
  });
  const shown = rows.slice(0, limit).map((r,i) => ({...r,rank:i+1}));
  return {
    rows: shown,
    count: shown.length,
    total: rows.length,
    season: season || "Historical Percentile",
    historical_scope: pctPrefix === "Historical",
    note: scope === "single"
      ? `Using the connected precomputed percentile source · ranked by ${stat}.`
      : `The connected API bridge currently exposes player-season percentile data; ${scope.replaceAll("_"," ")} aggregation remains on the legacy API contract.`,
    season_options: [...new Map(all.filter(r => !seasonType || String(r.Season_Type || "Regular Season") === seasonType).map(r => [r.Season,{value:r.Season,label:r.Season}])).values()]
  };
};


export async function getPlayerPeakProfile(playerId, seasonType = "Regular Season") {
  const params = new URLSearchParams({
    season_type: seasonType,
    season: "5-Year Peak",
  });
  const res = await fetch(`/api/v1/players/${encodeURIComponent(playerId)}/profile?${params.toString()}`);
  if (!res.ok) throw new Error(`Peak profile request failed: ${res.status}`);
  return res.json();
}

export const getPlayoffPeakDiagnostics = () => get("/playoff-peak-diagnostics");


// Phase 5A: deduplicate identical Playoff profile requests. The profile UI can
// mount/re-render more than once while switching context; sharing the same
// in-flight Promise prevents duplicate backend work without changing any data
// or headshot logic. The caller still receives the exact same payload.
const __playoffProfileInflight = new Map();
const __playoffProfileCache = new Map();
const __PLAYOFF_PROFILE_CACHE_TTL = 10 * 60 * 1000;

function __playoffProfileRequestKey(playerId, seasonType, season, percentileContext) {
  return [String(playerId ?? ""), String(seasonType ?? ""), String(season ?? ""), String(percentileContext ?? "")].join("|");
}

function __fetchPlayoffProfileOnce(playerId, seasonType, season, percentileContext) {
  const key = __playoffProfileRequestKey(playerId, seasonType, season, percentileContext);
  const cached = __playoffProfileCache.get(key);
  if (cached && Date.now() - cached.time < __PLAYOFF_PROFILE_CACHE_TTL) return Promise.resolve(cached.data);
  if (cached) __playoffProfileCache.delete(key);
  const existing = __playoffProfileInflight.get(key);
  if (existing) return existing;

  const params = new URLSearchParams({season_type: seasonType, season, percentile_context: percentileContext});
  const promise = get(`/players/${encodeURIComponent(playerId)}/profile?${params.toString()}`)
    .then(data => {
      __playoffProfileCache.set(key, {time: Date.now(), data});
      return data;
    })
    .finally(() => {
      if (__playoffProfileInflight.get(key) === promise) __playoffProfileInflight.delete(key);
    });
  __playoffProfileInflight.set(key, promise);
  return promise;
}

export async function getPlayerProfileBundle(playerId, seasonType = "Regular Season", season = "Career", percentileContext = "Season", signal) {
  // Regular-season Career and individual seasons are already in the indexed
  // public layer. Five-Year Peak remains on the canonical legacy endpoint.
  if (seasonType === "Regular Season" && String(season || "Career").toLowerCase() !== "5-year peak") {
    const bundles = await getPlayerSeasonBundles(playerId, seasonType);
    if (bundles?.found === false) throw new Error("Player profile was not found.");
    if (String(season || "Career").toLowerCase() === "career" && bundles?.career) return bundles.career;
    const row = (bundles?.rows || []).find(x => String(x?.season) === String(season));
    if (row?.bundle) return row.bundle;
    throw new Error("Requested player profile view is unavailable.");
  }
  // Playoff profile requests are shared by exact context. We intentionally do
  // not abort the shared network request when one UI subscriber unmounts; a
  // second subscriber may already be waiting on the same payload. Individual
  // callers still ignore stale results via the PlayerProfile request id.
  if (String(seasonType).toLowerCase().includes("playoff")) {
    return __fetchPlayoffProfileOnce(playerId, seasonType, season, percentileContext);
  }
  const params = new URLSearchParams({season_type: seasonType, season, percentile_context: percentileContext});
  // Peak reads join the same response/in-flight cache as prefetches. The
  // canonical endpoint and payload are unchanged; this only removes duplicate
  // network work during fast context transitions.
  return get(`/players/${encodeURIComponent(playerId)}/profile?${params.toString()}`);
}

export const getExplorerPopulation = async (xStatistic="PTS_per75", yStatistic="rTS", opts={}, signal) => {
  const qs = new URLSearchParams({
    x_statistic:xStatistic, y_statistic:yStatistic,
    season:opts.season || "Historical Percentile",
    season_type:opts.seasonType || "Regular Season",
    scope:opts.scope || "single", era:opts.era || "", search:opts.search || "",
    limit:String(opts.limit || 100),
  });
  ["x_min","x_max","y_min","y_max"].forEach(k=>{ if(opts[k] !== "" && opts[k] != null) qs.set(k,String(opts[k])); });
  return getWithSignal(`/public/explorer?${qs.toString()}`, signal);
};

export const getPlayerComparison = async (playerA, playerB, startA="", endA="", startB="", endB="", seasonType="Regular Season", context="Season", signal) => {
  const qs = new URLSearchParams({player_a:playerA,player_b:playerB,season_type:seasonType,context});
  if(startA) qs.set("start_a",startA);
  if(endA) qs.set("end_a",endA);
  if(startB) qs.set("start_b",startB);
  if(endB) qs.set("end_b",endB);
  return getWithSignal(`/compare?${qs.toString()}`,signal);
};

export async function getTeams(search="", season="", seasonType="Regular Season", era="", statistic="rDRtg", direction="asc"){
  return get(`/teams?search=${encodeURIComponent(search)}&season=${encodeURIComponent(season)}&season_type=${encodeURIComponent(seasonType)}&era=${encodeURIComponent(era)}&statistic=${encodeURIComponent(statistic)}&direction=${encodeURIComponent(direction)}`);
}
export async function getTeamProfile(team, season="", seasonType="Regular Season"){
  return get(`/teams/${encodeURIComponent(team)}?season=${encodeURIComponent(season)}&season_type=${encodeURIComponent(seasonType)}`);
}

export async function getTeamAnalytics(search="", season="", seasonType="Regular Season", statistic="rDRtg", direction="desc", limit=100, era=""){
  return get(`/teams/analytics?search=${encodeURIComponent(search)}&season=${encodeURIComponent(season)}&season_type=${encodeURIComponent(seasonType)}&statistic=${encodeURIComponent(statistic)}&direction=${encodeURIComponent(direction)}&limit=${limit}&era=${encodeURIComponent(era)}`);
}

export async function getTeamAnalyticsProfile(team="", season="", seasonType="Regular Season", scope="season"){
  return get(`/teams/profile?team=${encodeURIComponent(team)}&season=${encodeURIComponent(season)}&season_type=${encodeURIComponent(seasonType)}&scope=${encodeURIComponent(scope)}`);
}
