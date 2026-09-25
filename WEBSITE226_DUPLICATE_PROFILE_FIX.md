# Website226 — Duplicate Player Profile Fix

The player identity registry contained duplicate public profiles for many
historical players. The duplicate rows commonly had separate website/source
Player_ID values while sharing the same NBA_Player_ID and public name (for
example Michael Jordan, Oscar Robertson, and Rick Barry).

The canonical identity registry now prefers `NBA_Player_ID` as the stable
identity key whenever it exists, falling back to the source Player_ID only
when no NBA ID is available. This preserves legitimate namesakes while
collapsing source/asterisk variants of the same NBA player into one public
profile.

Verified:
- Michael Jordan: 1 public profile instead of 2
- Oscar Robertson: 1 public profile instead of 2
- Rick Barry: 1 public profile instead of 2
- Tiny Archibald: 1 public profile instead of 2
- Legacy duplicate IDs resolve back to the same canonical identity.

No SDI formula values were changed in this build. The proposed SDI missing-data
methodology is documented separately and should only be implemented after the
methodology is approved.
