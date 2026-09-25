"""Complete read-only Career SDI v4 audit.

Usage:
  python local_api/audit_career_sdi_v2.py --player "Rudy Gobert"

This audit does not overwrite any SDI cache. It reconstructs the complete
Career SDI v4 WOWY category inputs, including career-level WOWY Offense,
WOWY Defense, and WOWY Net, and compares them with the precomputed Career
SDI axes used by the Profile.
"""
from pathlib import Path
import argparse, json, math, sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local_api"))
import nba_per75_local_api as api

TOP = {
    "scoring_volume": .20,
    "scoring_efficiency": .18,
    "creation_playmaking": .18,
    "rebounding": .105,
    "defense": .20,
    "impact_value": .135,
}
SPEC = {
    "scoring_volume": {
        "Primary Scoring Output": {"weight": .35, "statistics": {"PTS_per75": 1.0}},
        "Scoring Composition": {"weight": .65, "statistics": {"FGA_per75": .55, "FTA_per75": .45}},
    },
    "scoring_efficiency": {
        "Overall Efficiency": {"weight": .60, "statistics": {"TS_pct": .25, "rTS": .75}},
        "Component Efficiency": {"weight": .40, "statistics": {"2P_pct": .5, "3P_pct": .4, "FT_pct": .1}},
    },
    "creation_playmaking": {
        "Creation Output": {"weight": .385, "statistics": {"AST_per75": .8, "AST_pct": .2}},
        "Ball Security / Creation Cost": {"weight": .315, "statistics": {"AST_TOV": .6, "TOV_pct": .4}},
        "WOWY Offensive Impact": {"weight": .30, "statistics": {"WOWY_Offense": 1.0}},
    },
    "rebounding": {
        "Rebounding Production": {"weight": .75, "statistics": {"ORB_per75": .45, "DRB_per75": .35, "TRB_per75": .2}},
        "Rebounding Rate": {"weight": .25, "statistics": {"OREB_pct": .45, "DREB_pct": .35, "TRB_pct": .2}},
    },
    "defense": {
        "Defensive Activity": {"weight": .35, "statistics": {"STL_per75": .5, "BLK_per75": .5}},
        "Defensive Activity Rate": {"weight": .25, "statistics": {"STL_pct": .5, "BLK_pct": .5}},
        "WOWY Defensive Impact": {"weight": .40, "statistics": {"WOWY_Defense": 1.0}},
    },
    "impact_value": {
        "WOWY Overall Impact": {"weight": 1.0, "statistics": {"WOWY_Net": 1.0}},
    },
}
LOWER_IS_BETTER = {"TOV_per75", "TOV_pct", "PF_per75", "DRtg", "Relative_DRtg"}
WOWY_COLS = ["WOWY_Offense", "WOWY_Defense", "WOWY_Net"]


def pct(vals, higher=True):
    s = pd.to_numeric(vals, errors="coerce")
    valid = s.dropna()
    out = pd.Series(np.nan, index=s.index, dtype=float)
    if valid.empty:
        return out
    ranks = valid.rank(method="average", ascending=not higher)
    n = len(valid)
    out.loc[valid.index] = 100.0 if n == 1 else 100.0 * (n - ranks) / (n - 1)
    return out


def _norm_name(s):
    return (s.astype(str).str.replace(r"\*+", "", regex=True)
            .str.strip().str.casefold())


def _wavg(g, value_col, weight_col="__mp"):
    v = pd.to_numeric(g.get(value_col, np.nan), errors="coerce")
    w = pd.to_numeric(g.get(weight_col, np.nan), errors="coerce")
    mask = v.notna() & w.notna() & w.gt(0)
    if not mask.any():
        return np.nan
    return float((v.loc[mask] * w.loc[mask]).sum() / w.loc[mask].sum())


def build_career_wowy(career):
    """Build complete career-level WOWY values using the canonical seasonal WOWY layer.

    The seasonal WOWY file does not carry minutes in all builds, so this joins
    the canonical regular-season player/season universe to obtain MP and then
    performs the same minutes-weighted career aggregation used by the API's
    career WOWY layer.
    """
    w = api._load_wowy_stat_layer()
    if w.empty:
        return career.copy(), {"available": False, "reason": "WOWY layer unavailable"}

    master = api.load_master_seasons()
    if master.empty:
        # Some completed builds expose MP directly in the WOWY layer. Use it if
        # available; otherwise report that a complete weighted reconstruction is
        # impossible rather than silently inventing weights.
        if "MP" not in w.columns:
            return career.copy(), {"available": False, "reason": "Master player-season layer unavailable and WOWY layer has no MP"}
        wm = w.copy()
    else:
        pcol = api.col(master, ["Player", "Player_Name", "Display_Name", "player_name", "Name"])
        scol = api.col(master, ["Season", "season", "Season_ID", "SeasonEndYear", "Season_End_Year"])
        mpcol = api.col(master, ["MP", "Minutes", "Minutes_Played"])
        pidcol = api.col(master, ["Player_ID", "PlayerId", "PlayerID", "player_id"])
        if not pcol or not scol or not mpcol:
            return career.copy(), {"available": False, "reason": "Canonical master layer lacks Player/Season/MP"}
        m = master[[c for c in [pcol, scol, mpcol, pidcol] if c]].copy()
        m["__namekey"] = _norm_name(m[pcol])
        m["__seasonkey"] = m[scol].map(api._season_label_any)
        m["__mp"] = pd.to_numeric(m[mpcol], errors="coerce")
        w2 = w.copy()
        w2["__namekey"] = _norm_name(w2["Player"])
        w2["__seasonkey"] = w2["Season"].astype(str).str.strip()
        keep = ["__namekey", "__seasonkey", "__mp"]
        if pidcol:
            keep.append(pidcol)
        m = m[keep].drop_duplicates(["__namekey", "__seasonkey"], keep="first")
        wm = w2.merge(m, on=["__namekey", "__seasonkey"], how="left")
        if "__mp_y" in wm.columns:
            wm["__mp"] = wm["__mp_y"]

    for c in WOWY_COLS:
        wm[c] = pd.to_numeric(wm.get(c, np.nan), errors="coerce")
    wm["__namekey"] = _norm_name(wm["Player"])
    wm = wm.loc[wm["__mp"].notna() & wm["__mp"].gt(0)].copy()
    vals = wm.groupby("__namekey", dropna=False).apply(
        lambda g: pd.Series({c: _wavg(g, c) for c in WOWY_COLS}), include_groups=False
    ).reset_index()

    out = career.copy()
    out["__namekey"] = _norm_name(out["Player"])
    out = out.merge(vals, on="__namekey", how="left", suffixes=("", "__wowy_reconstructed"))
    # Prefer the reconstructed career WOWY values when available; otherwise
    # preserve any canonical career WOWY value already present.
    for c in WOWY_COLS:
        old = pd.to_numeric(out[c], errors="coerce") if c in out.columns else pd.Series(np.nan, index=out.index)
        new = pd.to_numeric(out.get(c + "__wowy_reconstructed", np.nan), errors="coerce")
        out[c] = new.where(new.notna(), old)
    out = out.drop(columns=["__namekey"] + [c + "__wowy_reconstructed" for c in WOWY_COLS], errors="ignore")
    coverage = {c: float(out[c].notna().mean()) if c in out.columns else 0.0 for c in WOWY_COLS}
    return out, {"available": True, "coverage": coverage}


def find_target(career, pid=None, name=None):
    if pid:
        hit = career[career["Player_ID"].astype(str).str.strip().eq(str(pid).strip())]
        if not hit.empty:
            return hit.iloc[0]
    if name:
        key = str(name).replace("*", "").strip().casefold()
        hit = career[_norm_name(career["Player"]).eq(key)]
        if not hit.empty:
            return hit.iloc[0]
    return None


def build_audit(pid=None, name=None):
    career = api._build_regular_career_table()
    if career.empty:
        raise RuntimeError("Canonical career table is unavailable in this build/runtime.")
    career, wowy_meta = build_career_wowy(career)
    target = find_target(career, pid, name)
    if target is None:
        raise RuntimeError(f"Player not found: {pid or name}")

    qualified = career.loc[career["Qualified_Career"].astype(bool)].copy() if "Qualified_Career" in career else career.iloc[0:0].copy()
    if qualified.empty:
        raise RuntimeError("No qualified career population is available.")

    stats = sorted({s for groups in SPEC.values() for g in groups.values() for s in g["statistics"]})
    pcts = {}
    for stat in stats:
        if stat in qualified.columns:
            pcts[stat] = pct(qualified[stat], higher=stat not in LOWER_IS_BETTER)

    target_index = target.name
    components = {}
    categories = {}
    category_coverage = {}
    for cat, groups in SPEC.items():
        group_scores = []
        intended = observed = 0.0
        comp = {}
        for group_name, group in groups.items():
            gw = float(group["weight"])
            intended += gw
            vals = []
            for stat, sw in group["statistics"].items():
                series = pcts.get(stat)
                value = series.loc[target_index] if series is not None and target_index in series.index else np.nan
                if pd.notna(value):
                    vals.append((float(value), float(sw)))
                    comp[stat] = float(value)
            if vals:
                denom = sum(w for _, w in vals)
                group_scores.append((sum(v*w for v,w in vals) / denom, gw))
                observed += gw
        if group_scores:
            denom = sum(w for _, w in group_scores)
            categories[cat] = sum(v*w for v,w in group_scores) / denom
            category_coverage[cat] = observed / intended if intended else 0.0
        components[cat] = comp

    overall_denom = sum(TOP[k] for k in categories)
    reconstructed = sum(categories[k] * TOP[k] for k in categories) / overall_denom if overall_denom else None

    authoritative = api._career_sdi_axes(str(target.get("Player_ID")), str(target.get("Player")))
    auth_map = {str(x.get("axis")): x.get("value") for x in authoritative}
    auth_by_cat = {
        "scoring_volume": auth_map.get("Scoring Volume"),
        "scoring_efficiency": auth_map.get("Scoring Efficiency"),
        "creation_playmaking": auth_map.get("Creation & Playmaking"),
        "rebounding": auth_map.get("Rebounding"),
        "defense": auth_map.get("Defense"),
        "impact_value": auth_map.get("Impact & Value"),
    }
    diff = {k: (categories.get(k) - auth_by_cat[k]) if categories.get(k) is not None and auth_by_cat.get(k) is not None else None for k in TOP}
    diagnosis = "MATCH" if all(v is None or abs(v) < 1e-7 for v in diff.values()) else "CAREER_AXIS_MISMATCH"

    return {
        "player": {"player_id": str(target.get("Player_ID")), "player_name": str(target.get("Player")), "games": target.get("G"), "minutes": target.get("MP"), "qualified_career": bool(target.get("Qualified_Career"))},
        "method": "career underlying values + complete career WOWY reconstruction -> career percentiles -> locked SDI v4 WOWY category weights",
        "category_weights": TOP,
        "wowy_career_reconstruction": wowy_meta,
        "defense": {
            "reconstructed": categories.get("defense"),
            "authoritative_precomputed": auth_by_cat.get("defense"),
            "difference": diff.get("defense"),
            "coverage": category_coverage.get("defense"),
            "components": components.get("defense", {}),
        },
        "creation_playmaking": {
            "reconstructed": categories.get("creation_playmaking"),
            "authoritative_precomputed": auth_by_cat.get("creation_playmaking"),
            "difference": diff.get("creation_playmaking"),
            "coverage": category_coverage.get("creation_playmaking"),
            "components": components.get("creation_playmaking", {}),
        },
        "impact_value": {
            "reconstructed": categories.get("impact_value"),
            "authoritative_precomputed": auth_by_cat.get("impact_value"),
            "difference": diff.get("impact_value"),
            "coverage": category_coverage.get("impact_value"),
            "components": components.get("impact_value", {}),
        },
        "all_categories": {k: {"reconstructed": categories.get(k), "authoritative_precomputed": auth_by_cat[k], "difference": diff[k], "coverage": category_coverage.get(k)} for k in TOP},
        "reconstructed_overall_sdi": reconstructed,
        "authoritative_category_axes": authoritative,
        "diagnosis": diagnosis,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--player", default=None)
    ap.add_argument("--player-id", default=None)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    if not args.player and not args.player_id:
        ap.error("Use --player or --player-id")
    result = build_audit(args.player_id, args.player)
    text = json.dumps(result, indent=2, default=lambda x: None if (isinstance(x, float) and math.isnan(x)) else x)
    print(text)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")

if __name__ == "__main__":
    main()
