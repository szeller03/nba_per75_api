NBA PER-75 Big Board v46

Changes from v45:
- Fixed Big Board row navigation: BigBoard now initializes useNavigate(), so clicking any row navigates directly to the player's profile.
- Kept the whole-row click/keyboard behavior and player-name navigation.
- Kept instantaneous 5-Year Peak behavior and did not change Career WOWY (user elected to move on from that issue for now).
- Adjusted secondary percentile visual treatment for rTS: visual color is semantically capped at -4 to +4, with 0 neutral, so modest positive rTS values such as +2.8/+3.1 do not appear as poor merely because of the historical percentile distribution.
- Other secondary statistics continue to use their percentile-based visual score.
- Preserved the right-to-left row gradient.
- No Player Profile functionality/data/calculation changes.
