# V23.3 — Resolver Function Signature Fix

V23.2 fixed the variable spelling inside the fallback branch, but the function
still accepted only `master`, so the loaded identity DataFrame was not in its
scope. V23.3 fixes the function signature and passes the already-loaded
identity DataFrame into `build_master_evidence()`.

No identity methodology changed.
No fuzzy matching or silent assignment is introduced.
