# Website159 — Player Profile repair

- Fixed the 5-Year Peak Player Profile render crash caused by referencing
  `name` before its initialization in the peak percentile renderer.
- Made identity alias resolution deterministic for duplicate public names.
- Ambiguous names are no longer silently mapped to whichever same-name player
  happens to sort first.
- Same-person/source-ID aliases are still collapsed when the public identity
  is unambiguous.
- Distinct people who genuinely share a name remain distinct profiles.
