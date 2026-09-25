
export function createProfileRequestManager() {
  let generation = 0;
  let active = null;
  const cache = new Map();

  function begin(key) {
    generation += 1;
    const id = generation;
    if (active?.controller) active.controller.abort();
    const controller = new AbortController();
    active = { id, controller, key };
    return { id, signal: controller.signal };
  }

  function isCurrent(id) {
    return active?.id === id;
  }

  function getCached(key) {
    return cache.get(key) ?? null;
  }

  function setCached(key, value) {
    cache.set(key, value);
  }

  function cancel() {
    if (active?.controller) active.controller.abort();
    active = null;
  }

  return { begin, isCurrent, getCached, setCached, cancel };
}

export function profileContextKey(playerId, seasonType, season, percentileContext) {
  return [
    String(playerId ?? ""),
    String(seasonType ?? "Regular Season"),
    String(season ?? "Career"),
    String(percentileContext ?? "Season"),
  ].join("|");
}
