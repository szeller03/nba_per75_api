
import { getPlayerProfileBundle } from "./api";
import { createProfileRequestManager, profileContextKey } from "./profileLoadManagerV1";

export const website78ProfileManager = createProfileRequestManager();

export async function loadWebsite78Profile({ playerId, seasonType, season, percentileContext }) {
  const key = profileContextKey(playerId, seasonType, season, percentileContext);
  const cached = website78ProfileManager.getCached(key);
  if (cached) return { key, cached: true, data: cached };

  const { id, signal } = website78ProfileManager.begin(key);
  const data = await getPlayerProfileBundle(playerId, seasonType, season, percentileContext, signal);

  if (!website78ProfileManager.isCurrent(id)) {
    const err = new Error("STALE_PROFILE_REQUEST");
    err.code = "STALE_PROFILE_REQUEST";
    throw err;
  }

  website78ProfileManager.setCached(key, data);
  return { key, cached: false, data };
}
