# Website141 — Headshot Registry Key Fix

## Root cause identified

The API's `PATHS` dictionary defines the headshot source under the key
`"headshots"`:

    "headshots": _headshot_dir or (ROOT / "player_headshots_final_v1")

But `_headshot_url_for()` was calling:

    load("headshot_registry", ...)

There was no `"headshot_registry"` key in `PATHS`. The resolver caught that
lookup failure in a broad exception handler and silently returned an empty
lookup. As a result, the T10/T25/T50/T75 matchup cards had no usable
`headshot_url`, and the fallback proxy also had no URL to fetch.

## Fix

Changed the resolver to call:

    load("headshots", ["headshot_registry", "headshot"])

This points it at the actual configured headshot directory while preserving
the filename matching logic.

The API file was Python-compile validated after the change.
