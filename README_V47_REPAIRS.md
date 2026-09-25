# NBA PER-75 Website V47 — Career + Era Filter Repair

This build continues V46 and addresses three items:

1. **Regular-season Career Big Board duplicates fixed.**
   - `nba_per75_career_v2.csv` contains both Regular Season and Playoffs career rows.
   - The regular-season Career Big Board now explicitly uses only Regular Season rows.
   - Identity mapping no longer reorders rows before career metrics are assigned.

2. **Playoff Career profile access hardened.**
   - Player Profile preserves an explicit `Career` selection when switching between Regular Season and Playoffs, making Playoff Career directly reachable.
   - The V46 corrected playoff career calculations remain in place.

3. **Big Board Era filter added.**
   - Seven project-defined eras are available:
     - 1951-52 → 1969-70
     - 1970-71 → 1979-80
     - 1980-81 → 1989-90
     - 1990-91 → 1999-00
     - 2000-01 → 2009-10
     - 2010-11 → 2019-20
     - 2020-21 → 2025-26
   - Selecting an era restricts the Single Season Big Board population to player-seasons from that era.
   - The percentile context automatically switches to Era when an era is selected, while still allowing the user to choose another context afterward.
   - Career scope disables the Era filter because a career can span multiple eras.

The underlying NBA_Per75 data files are not modified.
