# V13 — Big Board API Syntax Fix

Fixed an indentation error in the Big Board dominance-index fallback that caused
`nba_per75_local_api.py` to fail with `SyntaxError: invalid syntax` at the
`except Exception:` block.

Python compilation was validated successfully.
No data or frontend logic was changed.
