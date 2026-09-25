# NBA PER-75 Website102 — Scatter Headshot Proxy Fix

The previous scatter implementation still depended on the browser directly
loading the headshot URL. That can fail even when the URL is valid because the
image host may reject browser referrers/CORS or because the URL is not directly
browser-loadable.

Website102 adds a same-origin local API proxy:
`/api/v1/players/{player}/headshot`

The API resolves the canonical headshot registry by Player ID/name, then:
- downloads remote HTTP(S) images server-side with a browser-like user agent,
  or
- reads a local image path when the registry supplies one,
and returns the image bytes with the correct content type.

The Explorer scatter now loads headshots through this local endpoint instead of
using the remote URL directly. This also means the scatter no longer depends
on `headshot_url` being present in the Big Board row.

If a headshot cannot be resolved, the underlying scatter point remains
available and the image simply disappears rather than breaking the chart.
