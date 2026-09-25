"""Static/runtime audit for the Player Profile SDI v4 formula."""
from nba_per75_local_api import (
    _load_sdi_v4_spec, _playoff_sdi_aggregation_spec,
    _percentile_rank_0_100, SDI_V4_TOP_LEVEL_WEIGHTS,
)

s = _load_sdi_v4_spec()
assert abs(sum(SDI_V4_TOP_LEVEL_WEIGHTS.values()) - 1.0) < 1e-12
assert s["scoring_efficiency"]["Overall Efficiency"]["weight"] == 0.65
assert s["scoring_efficiency"]["Overall Efficiency"]["statistics"] == {"rTS": 1.0}
assert s["scoring_efficiency"]["Component Efficiency"]["weight"] == 0.35
assert s["scoring_efficiency"]["Component Efficiency"]["statistics"] == {"2P_pct": .50, "3P_pct": .40, "FT_pct": .10}
assert s["creation_playmaking"]["Ball Security / Creation Cost"]["statistics"] == {"AST_TOV": 1.0}
assert s["defense"]["Defensive Activity"]["statistics"] == {"BLK_per75": .65, "STL_per75": .35}
assert s["defense"]["Defensive Activity Rate"]["statistics"] == {"BLK_pct": .65, "STL_pct": .35}
p = _playoff_sdi_aggregation_spec()
assert p["scoring_efficiency"] == s["scoring_efficiency"]
assert "defense" not in p and "impact_value" not in p
assert _percentile_rank_0_100(100, [1, 2, 3, 100]) == 100.0
assert _percentile_rank_0_100(1, [1, 2, 3, 100]) == 0.0
print("SDI v4 audit PASS")
print("Top-level weights:", SDI_V4_TOP_LEVEL_WEIGHTS)
print("Scoring Efficiency:", s["scoring_efficiency"])
print("Creation Ball Security:", s["creation_playmaking"]["Ball Security / Creation Cost"])
print("Playoff exclusions: Defense, Impact / Value")
