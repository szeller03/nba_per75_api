// Website240 frontend performance layer v1.
// Keeps the existing data/methodology intact while reducing repeated API work
// during a browsing session. Only successful JSON GET responses from the local
// API are cached, and cache entries expire quickly so filters/data changes are
// never treated as permanent.
(function installPerformanceFetchCache(){
  if (typeof window === 'undefined' || !window.fetch || window.__NBA75_PERF_FETCH__) return;
  const originalFetch = window.fetch.bind(window);
  const cache = new Map();
  const TTL = 10 * 60 * 1000;
  const MAX = 128;
  const isApiGet = (input, init) => {
    const method = String((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    if (method !== 'GET') return false;
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    return /127\.0\.0\.1:8000|localhost(?::\d+)?/.test(url) && /(?:api|player|board|spider|season|stat|team|explorer|compare)/i.test(url);
  };
  const keyFor = input => typeof input === 'string' ? input : input.url;
  const cloneFromEntry = entry => new Response(entry.body.slice(0), {status:entry.status,statusText:entry.statusText,headers:entry.headers});
  window.fetch = async function(input, init){
    if (!isApiGet(input, init)) return originalFetch(input, init);
    const key = keyFor(input);
    const now = Date.now();
    const hit = cache.get(key);
    if (hit && now - hit.time < TTL) {
      cache.delete(key); cache.set(key, hit);
      return cloneFromEntry(hit);
    }
    if (hit) cache.delete(key);
    const response = await originalFetch(input, init);
    if (!response.ok) return response;
    const type = response.headers.get('content-type') || '';
    if (!/json/i.test(type)) return response;
    const body = new Uint8Array(await response.clone().arrayBuffer());
    cache.set(key, {time:Date.now(), body, status:response.status, statusText:response.statusText, headers:new Headers(response.headers)});
    while (cache.size > MAX) cache.delete(cache.keys().next().value);
    return response;
  };
  window.__NBA75_PERF_FETCH__ = {clear:()=>cache.clear(), size:()=>cache.size};
})();
