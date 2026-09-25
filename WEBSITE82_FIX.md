# Website82 — Definitive Profile Bundle Import Fix

Website81 could still report `getPlayerProfileBundle is not defined` because
the prior patch did not robustly handle the existing App.jsx import structure.

Website82 adds an unconditional direct ES-module import at the top of App.jsx:

import { getPlayerProfileBundle } from "./api.js";

It also guarantees the helper and its signal-aware fetch dependency exist in
src/api.js.

No data or calculation logic changed.
