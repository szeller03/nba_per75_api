# V70 — Profile Registry Object Fix

The remaining React error identifies a statistic-registry metadata object being
rendered directly as a child. V70 normalizes registry entries in every profile
statistic table before JSX renders them, including the playoff branch, and also
normalizes season entries used by the season selector.

No calculations or source data are changed.
