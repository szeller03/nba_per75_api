# V67 — Precomputed 5-Year Peak Profile Integration

The 915-player precomputed dataset must live inside the SAME website project
whose local API you are running.

If your current website is:
C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website67

copy this folder:
C:\Users\szell\OneDrive\Desktop\NBA_Per75\data\precomputed_5_year_peak

to:
C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website67\data\precomputed_5_year_peak

The final target must be:
C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website67\data\precomputed_5_year_peak\regular_profile_peaks.json

Then replace/use the V67 local_api and frontend files from this build.

After starting the API, Player Profile -> 5-Year Peak reads ONE JSON record
for the selected player. It does not calculate the peak during the request.

The existing Big Board peak implementation is not changed in this build.
Playoff 5-Year Peak is also not changed; this integration is for the
precomputed regular-season Player Profile peak.
