# Website81 — Profile Bundle Import Fix

Website80 had the profile-loading architecture but App.jsx did not import
getPlayerProfileBundle from ./api, producing:

getPlayerProfileBundle is not defined

Website81 restores the named import and verifies the API helper exists.
No profile data, peak calculations, SDI, percentiles, or spider logic was
changed.
