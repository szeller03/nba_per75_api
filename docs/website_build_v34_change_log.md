# V34 — Playoff Percentile Non-Unique Index Fix

V33 failed while constructing the season-wide percentile table because the
underlying playoff statistical layer contains multiple team rows for some
player-seasons. Reindexing against that duplicate MultiIndex is invalid in
pandas.

V34 explicitly groups the season percentile output by:
Player_ID + Season + Season_Type

before constructing the wide table.

This is a presentation/storage normalization step only. The underlying
playoff statistical layer and identity decisions are unchanged.
