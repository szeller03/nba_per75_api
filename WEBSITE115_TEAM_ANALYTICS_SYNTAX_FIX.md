# Website115 — Team Analytics Syntax Fix

Website114 contained a JSX syntax error in the Team statistic-card `.map()`
callback. The callback closed the returned JSX but did not close the
JavaScript block expression correctly before the surrounding section.

The compiler reported:
`Expected "}" but found "className"` at the following `<section>`.

Website115 closes the `.map()` callback correctly and includes
`analysis/verify_frontend_build_v1.py` for a repeatable `npm run build` check.
No Team analytics data logic was changed.
