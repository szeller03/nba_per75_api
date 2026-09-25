# Team Competitive Context V9

Fixes V8 browser acquisition failure. Basketball-Reference 429 pages are detected before pandas parsing; HTML is passed through StringIO so pandas never treats the HTML as a filename. Use --interactive-fallback when the source blocks automated browser acquisition. This opens a visible Chrome/Edge window and lets the user resolve the page, then captures the DOM through Chrome DevTools Protocol.

Run: `python local_api/build_team_competitive_context_v9.py --interactive-fallback`
