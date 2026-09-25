# Website128 — Era Filter + Global Dark Filters

## Era filter
Website127's Teams component passed the era to getTeamAnalytics, and the
backend supported an era parameter, but src/api.js did not include the era
query parameter. Therefore the UI changed while the API continued receiving
an empty era and returned the full historical population.

Website128 fixes the API wrapper so `era=<selected era>` is actually sent.
Changing Era also clears a previously selected Season because the two filters
should not silently conflict.

## Filter styling
Global `select` and `option` styling is restored in both primary stylesheets:
black background, white text, and dark native color scheme.
