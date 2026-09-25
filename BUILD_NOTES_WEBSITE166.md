# Website166 — eliminate first-load local API race

The remaining behavior — Player Profile fails on the first attempt but works
after refresh — was traced to API startup ordering.

Previously the local API did not bind to port 8000 until after:
- Big Board cache warm
- NEW SDI v4 season index warm
- playoff 5-Year Peak cache warm

The frontend could therefore send its first profile request while the API was
still warming and before anything was listening on port 8000.

Fixes:
1. The HTTP server now binds/listens immediately.
2. Big Board, NEW SDI v4, and playoff peak caches warm in a background thread.
3. The frontend API helper now retries transient 5xx/connection failures with
   short delays (250ms, 600ms, 1200ms).
4. Intentional AbortController cancellations are never retried.
5. Normal 4xx errors are still returned immediately.

The duplicate-player fix and NEW SDI v4 5-Year Peak implementation from the
previous build are retained.
