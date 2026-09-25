# V7 — API Export Fix

Fixed the V6 frontend build failure caused by App.jsx importing `getStatisticRegistry` while src/api.js did not export it.

Added:
- `getStatisticRegistry()` frontend API function.
- Backend fallback to the 46-stat taxonomy if the separate statistic registry CSV is unavailable.

No analytical source data was modified.
