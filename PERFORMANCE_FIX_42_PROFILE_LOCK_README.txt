Website240 Performance Fix 42 — Profile Performance Lock

BASELINE
This package restores and locks the known-good Fix 36/40 Player Profile performance architecture.

RULE
Player Profiles are a protected regression surface. Future performance work must not modify the profile request/rendering path unless explicitly intended and separately benchmarked.

PRESERVED
- Career spider response-ready cache
- Career SDI/WOWY axes cache
- Season-bundle optimization
- Existing profile request/render behavior
- SDI v4 / WOWY / qualification / peak methodology
- Existing headshot system
- Fix 32 SQLite handling
- Fix 34/36 performance work

NOT INCLUDED
- Fix 41 frontend request-orchestration changes
- Fix 38/39 experimental Big Board cache changes

NEXT PERFORMANCE WORK
Optimize Big Board, search request frequency, compare-page latency, and frontend assets independently. Run profile regression tests after every build.
