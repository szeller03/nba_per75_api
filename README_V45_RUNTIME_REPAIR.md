# V45 — Runtime Repair: Playoff Requests, Career Board, and Profile Loading

This repair addresses the V44 runtime problems observed during live testing:

1. Normal playoff profile requests no longer build the full playoff career table.
2. The finalized playoff 46-stat season layer is used directly when available,
   avoiding an expensive reconstruction of the raw playoff master on first UI use.
3. Career Big Board requests bypass season-percentile column validation and use
   the canonical regular-season career layer when available.
4. Playoff source discovery is cached after the first lookup.

The API data-path diagnostics remain unchanged.
