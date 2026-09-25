# V65 — Player Profile 5-Year Peak Final Repair

Focused exclusively on Player Profiles.

Changes:
- Peak profile path now prefers an SDI field already present in the player's master rows.
- If no SDI field exists, the dominance source is loaded once into the API cache instead of being repeatedly read for profile requests.
- Peak window evaluation remains the locked canonical rule: five qualifying seasons within six calendar seasons, one skipped season allowed, selected by highest five-season average SDI.
- Player Profile auxiliary Spider and Context requests now wait until the main profile response exists, so a slow auxiliary endpoint cannot make the profile appear stuck while the main data is loading.
- Big Board implementation is untouched.

API syntax verified successfully.
