# NBA PER-75 Website107 — Team Auto-Build / No-Stuck Loading

The previous Team page required a manual precompute step. If that step was
not run, the UI could remain in its loading state depending on the frontend
build.

Website107 removes that dependency:
- The first `/api/v1/teams` request immediately returns `status=building`.
- A daemon background thread starts the existing canonical precompute script.
- The frontend polls once per second while the compact index is being built.
- When the cache is ready, the Team page automatically renders.
- If the build fails, the UI displays the actual error instead of loading
  indefinitely.
- A two-minute frontend polling ceiling prevents an endless client loop.
- Once built, subsequent Team requests use the compact JSON cache and are
  fast.

This preserves the precomputed architecture while making the Team page
self-starting.
