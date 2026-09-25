NBA PER-75 — FIX62

Target: NBA_Per75_Website242

This is a surgical three-part Profile fix based on the Website242 source baseline.
It does NOT rebuild or alter the underlying SDI/statistical data, headshot files, or methodology.

1) PLAYER HEADSHOTS
   - Profile Headshot now honors the canonical headshot_url returned by the profile API.
   - It tries canonical local headshot -> named override -> profile-provided URL -> API headshot endpoint.
   - This prevents the 5-Year Peak profile response from falling back to initials when the profile's
     player object contains a valid headshot URL.

2) PLAYOFF 5-YEAR PEAK SDI
   - Initializes the playoff peak spider category_axes before conditional processing, preventing an
     empty/malformed peak percentile payload from causing an UnboundLocalError/500.
   - Playoff peak category axes explicitly expose their percentile-scale value.
   - The canonical playoff peak response now includes the canonical headshot URL.

3) INDIVIDUAL PLAYOFF PERCENTILES
   - The public SQLite season-bundle endpoint previously returned playoff rows with an empty
     percentiles array because that indexed layer only stores regular-season percentiles.
   - Playoff season-bundle requests now use the existing canonical playoff profile/percentile engine,
     preserving the finalized playoff percentile methodology while keeping regular-season bundles on
     the fast public layer.

Files to replace:
   src/App.jsx
   local_api/nba_per75_local_api.py

No other files are intended to change.

Validation:
   - Python compilation passed for nba_per75_local_api.py.
   - ZIP contains only the two replacement source files plus this README.
