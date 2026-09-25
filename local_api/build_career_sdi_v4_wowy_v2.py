"""Rebuild the canonical regular-season Career SDI v4 WOWY layer.

This replaces the legacy/precomputed Career SDI axes with the locked Career
methodology:
  career underlying values -> career percentiles -> locked SDI v4 weights.

Career WOWY Offense/Defense/Net values are taken from the existing canonical
career aggregation in nba_per75_local_api._build_regular_career_table(); no
new WOWY aggregation methodology is introduced here.

Usage:
  python local_api/build_career_sdi_v4_wowy_v2.py

The output is written to:
  data/regular_career_sdi_v4_wowy_rts.csv
A timestamped backup is created first when the existing output exists.
"""
from pathlib import Path
import json, shutil, sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local_api"))
import nba_per75_local_api as api
from audit_career_sdi_v2 import build_career_wowy

TOP = {
    "scoring_volume": 0.22,
    "scoring_efficiency": 0.20,
    "creation_playmaking": 0.20,
    "rebounding": 0.105,
    "defense": 0.22,
    "impact_value": 0.055,
}

def load_locked_spec():
    """Load the project's current authoritative SDI subcategory specification.

    The top-level category weights remain the explicit 22/20/20/10.5/22/5.5
    weights above. The CSV controls the within-category/group/statistic weights.
    """
    spec_path = ROOT / "player_subcategory_aggregation_v1" / "player_subcategory_aggregation_spec_v1.csv"
    if not spec_path.exists():
        raise RuntimeError(f"Missing authoritative SDI aggregation spec: {spec_path}")
    df = pd.read_csv(spec_path, low_memory=False)
    cat = col(df, ["Category"])
    group = col(df, ["Group_ID", "Group", "Group_Id"])
    stat = col(df, ["Statistic", "Stat"])
    sw = col(df, ["Statistic_Weight", "Stat_Weight", "Within_Group_Weight"])
    gw = col(df, ["Group_Weight"])
    if not all([cat, group, stat, sw, gw]):
        raise RuntimeError("Aggregation spec is missing required columns.")
    out = {}
    aliases = {
        "scoring volume": "scoring_volume",
        "scoring efficiency": "scoring_efficiency",
        "efficiency": "scoring_efficiency",
        "creation / playmaking": "creation_playmaking",
        "creation & playmaking": "creation_playmaking",
        "rebounding": "rebounding",
        "defense": "defense",
        "impact / value": "impact_value",
        "impact & value": "impact_value",
    }
    for category, cg in df.groupby(cat, sort=False):
        key = aliases.get(str(category).strip().casefold())
        if not key:
            continue
        groups = {}
        for group_name, gg in cg.groupby(group, sort=False):
            first = gg.iloc[0]
            groups[str(group_name)] = {
                "weight": float(first[gw]),
                "statistics": {
                    str(r[stat]).strip(): float(r[sw])
                    for _, r in gg.iterrows()
                    if pd.notna(r[sw])
                },
            }
        out[key] = groups
    return out

SPEC = load_locked_spec()


LOWER_IS_BETTER = {"TOV_per75", "TOV_pct", "PF_per75", "DRtg", "Relative_DRtg"}


def col(df, candidates):
    """Return the first matching column name from a list of canonical aliases."""
    if df is None:
        return None
    lookup = {str(c).strip().casefold(): c for c in df.columns}
    for candidate in candidates:
        hit = lookup.get(str(candidate).strip().casefold())
        if hit is not None:
            return hit
    return None


def percentile(series, higher=True):
    s = pd.to_numeric(series, errors="coerce")
    valid = s.dropna()
    out = pd.Series(np.nan, index=s.index, dtype=float)
    if valid.empty:
        return out
    ranks = valid.rank(method="average", ascending=not higher)
    n = len(valid)
    out.loc[valid.index] = 100.0 if n == 1 else 100.0 * (n - ranks) / (n - 1)
    return out


def main():
    out_path = ROOT / "data" / "regular_career_sdi_v4_wowy_rts.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        backup = out_path.with_name(out_path.stem + ".pre_50_6_backup.csv")
        if not backup.exists():
            shutil.copy2(out_path, backup)

    career = api._build_regular_career_table().copy()
    if career.empty:
        raise RuntimeError("Canonical regular career table is empty.")

    required_identity = [c for c in ["Player_ID", "Player"] if c not in career.columns]
    if required_identity:
        raise RuntimeError(f"Career table missing required columns: {required_identity}")

    # Use the exact canonical career WOWY reconstruction already exercised by the
    # complete audit. The production rebuild and audit therefore consume the same
    # player-season WOWY layer and MP weighting rather than maintaining two methods.
    career, wowy_meta = build_career_wowy(career)
    if not wowy_meta.get("available"):
        raise RuntimeError(f"Canonical Career WOWY layer unavailable: {wowy_meta.get('reason', 'unknown reason')}")

    g = pd.to_numeric(career.get("G", np.nan), errors="coerce")
    mp = pd.to_numeric(career.get("MP", np.nan), errors="coerce")
    career["Qualified_Career"] = g.ge(400) & mp.ge(10000)
    qualified = career.loc[career["Qualified_Career"]].copy()
    if qualified.empty:
        raise RuntimeError("No qualified Career population is available.")

    stats = sorted({s for groups in SPEC.values() for group in groups.values() for s in group["statistics"]})
    pct = {}
    # Some canonical career files do not materialize TRB% even though the
    # player-season profile layer carries the canonical season-level TRB%.
    # Resolve that field before percentile generation rather than failing the
    # entire rebuild. Prefer a direct canonical career alias when present;
    # otherwise construct the career rate as an MP-weighted aggregation of the
    # canonical regular-season player-season TRB% values.
    if "TRB_pct" not in qualified.columns:
        trb_alias = col(qualified, ["TRB_pct", "TRB%", "TRB_pct.1"])
        if trb_alias:
            qualified["TRB_pct"] = pd.to_numeric(qualified[trb_alias], errors="coerce")
        else:
            prof_path = ROOT / "player_profiles_v1" / "player_season_profiles.csv"
            if not prof_path.exists():
                raise RuntimeError(
                    "Canonical Career table is missing SDI input: TRB_pct and "
                    "the canonical player-season profile layer is unavailable "
                    "for deriving it."
                )
            prof = pd.read_csv(prof_path, low_memory=False)
            pst = col(prof, ["Season_Type", "SeasonType", "season_type", "Phase"])
            if pst:
                vals = prof[pst].astype(str).str.strip().str.casefold()
                prof = prof.loc[vals.isin({"regular season", "regular", "reg season"})].copy()
            pp_id = col(prof, ["Player_ID", "PlayerId", "PlayerID", "player_id"])
            pp_mp = col(prof, ["MP", "Minutes", "minutes"])
            pp_trb = col(prof, ["TRB_pct", "TRB%", "TRB_pct.1"])
            if not pp_id or not pp_mp or not pp_trb:
                raise RuntimeError(
                    "Canonical Career table is missing SDI input: TRB_pct and "
                    "the player-season profile layer does not contain the fields "
                    "needed to derive it."
                )
            prof["__pid"] = prof[pp_id].astype(str).str.strip()
            prof["__mp"] = pd.to_numeric(prof[pp_mp], errors="coerce")
            prof["__trb_pct"] = pd.to_numeric(prof[pp_trb], errors="coerce")
            prof = prof.loc[prof["__mp"].notna() & prof["__mp"].gt(0) & prof["__trb_pct"].notna()].copy()
            trb_map = prof.groupby("__pid", sort=False).apply(
                lambda g: float((g["__trb_pct"] * g["__mp"]).sum() / g["__mp"].sum()),
                include_groups=False,
            ).to_dict()
            qualified["TRB_pct"] = qualified["Player_ID"].astype(str).str.strip().map(trb_map)

    for stat in stats:
        if stat not in qualified.columns:
            raise RuntimeError(f"Canonical Career table is missing SDI input: {stat}")
        pct[stat] = percentile(qualified[stat], higher=stat not in LOWER_IS_BETTER)

    # Evidence gate for historically sparse tracking statistics.
    #
    # Career SDI must not treat a statistic observed in only a small fraction
    # of a player's career as representative of the whole career.  The gate is
    # based on minutes coverage in the canonical player-season profile layer.
    # Unavailable evidence is removed before the category is formed; the
    # remaining group/category weights are then renormalized.
    tracking_stats = {"STL_per75": "STL_raw", "BLK_per75": "BLK_raw", "STL_pct": "STL_raw", "BLK_pct": "BLK_raw", "3P_pct": "3P_raw"}
    coverage_map = {}
    prof_path = ROOT / "player_profiles_v1" / "player_season_profiles.csv"
    if prof_path.exists():
        prof = pd.read_csv(prof_path, low_memory=False)
        pst = col(prof, ["Season_Type", "SeasonType", "season_type", "Phase"])
        if pst:
            vals = prof[pst].astype(str).str.strip().str.casefold()
            prof = prof.loc[vals.isin({"regular season", "regular", "reg season"})].copy()
        pidc = col(prof, ["Player_ID", "PlayerId", "PlayerID", "player_id"])
        mpc = col(prof, ["MP", "Minutes", "minutes"])
        if pidc and mpc:
            prof["__pid"] = prof[pidc].astype(str).str.strip()
            prof["__mp"] = pd.to_numeric(prof[mpc], errors="coerce").fillna(0.0)
            for stat, raw_col in tracking_stats.items():
                rc = col(prof, [raw_col, stat, stat.replace("_per75", ""), stat.replace("_pct", "")])
                if not rc:
                    continue
                prof["__obs"] = pd.to_numeric(prof[rc], errors="coerce")
                for pid_key, gg in prof.groupby("__pid", sort=False):
                    total_mp = float(gg["__mp"].sum())
                    observed_mp = float(gg.loc[gg["__obs"].notna() & gg["__mp"].gt(0), "__mp"].sum())
                    coverage_map.setdefault(pid_key, {})[stat] = observed_mp / total_mp if total_mp > 0 else 0.0

    # A statistic with <50% career-minute coverage is unavailable for Career
    # SDI. For 3P%, this prevents a player with little/no meaningful 3-point
    # history from being penalized by a misleading career percentage.
    for idx in qualified.index:
        pid_key = str(qualified.at[idx, "Player_ID"]).strip()
        covs = coverage_map.get(pid_key, {})
        for stat in tracking_stats:
            cov = covs.get(stat)
            if cov is not None and cov < 0.50:
                pct[stat].loc[idx] = np.nan

    # Preserve the existing output's non-SDI columns where possible, but use
    # the canonical career population/identity as the source of truth.
    existing = pd.read_csv(out_path, low_memory=False) if out_path.exists() else pd.DataFrame()
    # Only restore genuinely legacy/non-authoritative columns.  Identity fields
    # and all WOWY/SDI fields are already authoritative in `rebuilt`; including
    # them here would create duplicate Player_x/Player_y and WOWY_*_x/WOWY_*_y
    # columns on merge (the exact failure seen in 50.7).
    authoritative = {
        "Player_ID", "Player", "Career_G", "Career_MP", "Qualified_Career",
        "Career_scoring_volume", "Career_scoring_efficiency",
        "Career_creation_playmaking", "Career_rebounding", "Career_defense",
        "Career_impact_value", "Career_scoring_volume_Coverage",
        "Career_scoring_efficiency_Coverage", "Career_creation_playmaking_Coverage",
        "Career_rebounding_Coverage", "Career_defense_Coverage",
        "Career_impact_value_Coverage", "SDI_Category_Coverage",
        "SDI_v4", "SDI_v4_WOWY", "Career_SDI_v4",
        "WOWY_Offense", "WOWY_Defense", "WOWY_Net",
    }
    keep_existing = [c for c in existing.columns if c not in authoritative]

    rows = []
    for idx, r in qualified.iterrows():
        cat_scores = {}
        cat_cov = {}
        for cat, groups in SPEC.items():
            group_scores = []
            intended = observed = 0.0
            for group in groups.values():
                gw = float(group["weight"])
                intended += gw
                vals = []
                for stat, sw in group["statistics"].items():
                    p = pct[stat]
                    val = p.loc[idx]
                    if pd.notna(val):
                        vals.append((float(val), float(sw)))
                if vals:
                    den = sum(w for _, w in vals)
                    group_scores.append((sum(v*w for v,w in vals)/den, gw))
                    observed += gw
            if group_scores:
                den = sum(w for _, w in group_scores)
                cat_scores[cat] = sum(v*w for v,w in group_scores)/den
                cat_cov[cat] = observed / intended if intended else 0.0
            else:
                cat_scores[cat] = np.nan
                cat_cov[cat] = 0.0

        available = [k for k in TOP if pd.notna(cat_scores[k])]
        den = sum(TOP[k] for k in available)
        overall = sum(cat_scores[k] * TOP[k] for k in available) / den if den else np.nan
        row = {
            "Player_ID": str(r["Player_ID"]).strip(),
            "Player": str(r["Player"]).strip(),
            "Career_G": float(g.loc[idx]) if pd.notna(g.loc[idx]) else np.nan,
            "Career_MP": float(mp.loc[idx]) if pd.notna(mp.loc[idx]) else np.nan,
            "Qualified_Career": True,
            "Career_scoring_volume": cat_scores["scoring_volume"],
            "Career_scoring_efficiency": cat_scores["scoring_efficiency"],
            "Career_creation_playmaking": cat_scores["creation_playmaking"],
            "Career_rebounding": cat_scores["rebounding"],
            "Career_defense": cat_scores["defense"],
            "Career_impact_value": cat_scores["impact_value"],
            "Career_scoring_volume_Coverage": cat_cov["scoring_volume"],
            "Career_scoring_efficiency_Coverage": cat_cov["scoring_efficiency"],
            "Career_creation_playmaking_Coverage": cat_cov["creation_playmaking"],
            "Career_rebounding_Coverage": cat_cov["rebounding"],
            "Career_defense_Coverage": cat_cov["defense"],
            "Career_impact_value_Coverage": cat_cov["impact_value"],
            "SDI_Category_Coverage": sum(TOP[k] * cat_cov[k] for k in TOP),
            "SDI_v4": overall,
            "SDI_v4_WOWY": overall,
            "Career_SDI_v4": overall,
            "WOWY_Offense": r.get("WOWY_Offense", np.nan),
            "WOWY_Defense": r.get("WOWY_Defense", np.nan),
            "WOWY_Net": r.get("WOWY_Net", np.nan),
        }
        rows.append(row)

    rebuilt = pd.DataFrame(rows)

    # Hard validation before the live Career SDI file is replaced. The rebuild
    # must retain complete WOWY inputs for Gobert and a non-null Impact & Value;
    # otherwise the build aborts before touching the output.
    _g = rebuilt.loc[rebuilt["Player"].astype(str).str.strip().str.casefold().eq("rudy gobert")]
    if _g.empty:
        raise RuntimeError("Pre-write validation failed: Rudy Gobert is not present in the rebuilt Career SDI population.")
    if not _g.empty:
        _gr = _g.iloc[0]
        for _wc in ["WOWY_Offense", "WOWY_Defense", "WOWY_Net"]:
            if pd.isna(pd.to_numeric(_gr.get(_wc, np.nan), errors="coerce")):
                raise RuntimeError(f"Pre-write validation failed: Rudy Gobert is missing {_wc} in the rebuilt Career SDI row.")
        if pd.isna(pd.to_numeric(_gr.get("Career_impact_value", np.nan), errors="coerce")):
            raise RuntimeError("Pre-write validation failed: Rudy Gobert Career_impact_value is null after complete WOWY reconstruction.")

    # Add back non-SDI columns from the old career layer by player ID when they
    # are not part of the newly authoritative calculation.
    if not existing.empty and "Player_ID" in existing.columns:
        ex = existing.copy()
        ex["Player_ID"] = ex["Player_ID"].astype(str).str.strip()
        extra = [c for c in keep_existing if c in ex.columns and c != "Player_ID"]
        if extra:
            ex2 = ex[["Player_ID"] + extra].drop_duplicates("Player_ID", keep="first")
            rebuilt = rebuilt.merge(ex2, on="Player_ID", how="left")

    # Preserve a stable, readable column order.
    first = [
        "Player_ID","Player","Career_G","Career_MP","Qualified_Career",
        "Career_scoring_volume","Career_scoring_efficiency","Career_creation_playmaking",
        "Career_rebounding","Career_defense","Career_impact_value",
        "Career_scoring_volume_Coverage","Career_scoring_efficiency_Coverage",
        "Career_creation_playmaking_Coverage","Career_rebounding_Coverage",
        "Career_defense_Coverage","Career_impact_value_Coverage",
        "SDI_Category_Coverage","SDI_v4","SDI_v4_WOWY","Career_SDI_v4",
        "WOWY_Offense","WOWY_Defense","WOWY_Net"
    ]
    cols = [c for c in first if c in rebuilt.columns] + [c for c in rebuilt.columns if c not in first]
    rebuilt = rebuilt[cols]
    rebuilt.to_csv(out_path, index=False)

    # Build a diagnostic target without assuming the rebuilt frame contains a
    # display-name column under one exact spelling.  The canonical identity is
    # Player_ID; use name aliases only as a fallback.  This also prevents the
    # diagnostic report from turning a successful rebuild into a post-write
    # KeyError/NameError.
    target = pd.DataFrame()
    name_col = col(rebuilt, ["Player", "Player_Name", "player_name", "Name"])
    if name_col is not None:
        target = rebuilt.loc[
            rebuilt[name_col].astype(str).str.strip().str.casefold().eq("rudy gobert")
        ].copy()
    report = {
        "version": "SDI_v4_WOWY_Career_v2",
        "method": "career underlying values -> career percentiles -> locked SDI v4 WOWY category weights",
        "qualified_career_population": int(len(qualified)),
        "output": str(out_path),
        "weights": TOP,
        "defense_subweights": {"Defensive Activity": .35, "Defensive Activity Rate": .25, "WOWY Defensive Impact": .40},
        "creation_subweights": {"Creation Output": .385, "Ball Security / Creation Cost": .315, "WOWY Offensive Impact": .30},
        "impact_subweights": {"WOWY Overall Impact": 1.0},
        "players_with_complete_sdi": int(rebuilt["SDI_v4_WOWY"].notna().sum()),
    }
    if not target.empty:
        t = target.iloc[0]
        report["rudy_gobert"] = {c: (None if pd.isna(t[c]) else float(t[c])) for c in [
            "Career_scoring_volume","Career_scoring_efficiency","Career_creation_playmaking",
            "Career_rebounding","Career_defense","Career_impact_value","SDI_v4_WOWY"
        ]}
    report_path = ROOT / "data" / "SDI_V4_WOWY_CAREER_BUILD_REPORT_V2.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
