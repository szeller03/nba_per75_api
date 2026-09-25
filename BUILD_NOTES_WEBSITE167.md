# Website167 — Explorer blank-page fix

The Explorer component was referencing `search` in:
- the primary Big Board data effect,
- the scatter data effect, and
- the Find Player input,

but Explorer never declared a `search` state variable.

That produces a React render-time `ReferenceError` when the Explorer route is
opened, which explains why the entire page appeared blank rather than showing
an API error.

Fix:
- Added `const [search,setSearch]=useState("")` to Explorer.
- No Explorer behavior or filtering logic was otherwise changed.
- Existing Player Profile duplicate fix, first-load API fix, and NEW SDI v4
  5-Year Peak implementation are retained.
