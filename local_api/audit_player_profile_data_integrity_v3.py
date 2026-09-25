"""
NBA PER-75 — Player Profile Data Integrity Audit v3

Purpose:
Schema-first, evidence-first integrity audit for Website241.

This version does NOT infer uniqueness from a generic Player+Season rule.
It first prints/records the actual schemas, identifies likely identity columns,
shows concrete duplicate samples, resolves the known peak files by exact
filename patterns, and performs cross-layer checks.

READ ONLY except for:
    data/player_profile_data_integrity_report_v3.json

Run:
    python local_api/audit_player_profile_data_integrity_v3.py <WEBSITE_ROOT>
"""

from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import pandas as pd
import numpy as np

KNOWN_FILES = {
    "master": "nba_per75_master_v46.csv",
    "career_sdi": "regular_career_sdi_v4_wowy_rts.csv",
    "regular_sdi": "regular_sdi_v4_wowy_player_seasons.csv",
    "playoff_sdi": "playoff_sdi_v4_player_seasons.csv",
    "regular_peak": "regular_profile_peaks_wowy_rts_v3_career_sdi.json",
    "playoff_peak": "playoff_profile_peaks_authoritative_v9.json",
    "wowy": "player_wowy_statistics_v1.csv",
    "percentiles": "player_season_percentiles_long_v2_1.csv",
}

PLAYER_CHECKS = [
    "Wilt Chamberlain", "Michael Jordan", "LeBron James",
    "Kareem Abdul-Jabbar", "Hakeem Olajuwon", "Bill Russell",
    "Tim Duncan", "Kevin Garnett", "Shaquille O'Neal",
    "Nikola Jokic", "Patrick Ewing", "Rudy Gobert",
    "Dennis Rodman", "David Robinson"
]

def norm(x):
    return re.sub(r"[^a-z0-9]+", "_", str(x).strip().lower()).strip("_")

def clean_name(x):
    return str(x).replace("*", "").strip()

def locate(root: Path, filename: str):
    exact = root / "data" / filename
    if exact.exists():
        return exact
    exact2 = root / "local_api" / "cache" / filename
    if exact2.exists():
        return exact2
    matches = list(root.rglob(filename))
    return matches[0] if matches else None

def locate_pattern(root: Path, patterns, extensions):
    candidates = []
    for p in root.rglob("*"):
        if p.suffix.lower() in extensions:
            n = p.name.lower()
            if all(part.lower() in n for part in patterns):
                candidates.append(p)
    candidates.sort(key=lambda p: (len(str(p)), str(p).lower()))
    return candidates[0] if candidates else None

def resolve_sources(root):
    result = {}
    for key, filename in KNOWN_FILES.items():
        result[key] = locate(root, filename)

    if result["regular_peak"] is None:
        result["regular_peak"] = locate_pattern(
            root, ["regular_profile_peaks", "wowy_rts"], {".json"}
        )
    if result["playoff_peak"] is None:
        result["playoff_peak"] = locate_pattern(
            root, ["playoff_profile_peaks_authoritative"], {".json", ".csv"}
        )
    return result

def read_csv(path):
    if not path:
        return None
    try:
        return pd.read_csv(path, low_memory=False)
    except Exception:
        return None

def read_json(path):
    if not path:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def find_col(df, names):
    if df is None:
        return None
    mapping = {norm(c): c for c in df.columns}
    for name in names:
        if norm(name) in mapping:
            return mapping[norm(name)]
    return None

def season_col(df):
    return find_col(df, [
        "Season", "season", "Season_ID", "SeasonId",
        "SeasonEndYear", "Season_End_Year", "Year", "year"
    ])

def season_type_col(df):
    return find_col(df, ["Season_Type", "season_type", "SeasonType"])

def player_col(df):
    return find_col(df, [
        "Player", "Player_Name", "Display_Name", "player_name", "Name"
    ])

def statistic_col(df):
    return find_col(df, [
        "Statistic", "statistic", "Stat", "Statistic_Name", "stat_name"
    ])

def id_candidates(name, df):
    if df is None:
        return []

    p = player_col(df)
    s = season_col(df)
    st = season_type_col(df)
    stat = statistic_col(df)

    # Candidate keys, not assumptions.
    candidates = []
    if p and s and st:
        candidates.append(("player_season_type", [p, s, st]))
    if p and s and stat and st:
        candidates.append(("player_season_stat_type", [p, s, stat, st]))
    if p and s and stat:
        candidates.append(("player_season_stat", [p, s, stat]))
    if p and s:
        candidates.append(("player_season", [p, s]))
    if p:
        candidates.append(("player_only", [p]))

    # If a canonical Player_ID exists, prefer it as identity component.
    pid = find_col(df, [
        "Player_ID", "PlayerId", "PlayerID", "player_id", "playerid"
    ])
    if pid and s and st:
        candidates.insert(0, ("player_id_season_type", [pid, s, st]))
    if pid and s and stat and st:
        candidates.insert(0, ("player_id_season_stat_type", [pid, s, stat, st]))
    if pid and s and stat:
        candidates.insert(0, ("player_id_season_stat", [pid, s, stat]))
    if pid and s:
        candidates.insert(0, ("player_id_season", [pid, s]))

    # Remove duplicate candidate definitions.
    seen = set()
    out = []
    for label, cols in candidates:
        tup = tuple(cols)
        if tup not in seen:
            seen.add(tup)
            out.append((label, cols))
    return out

def evaluate_keys(df, candidates):
    results = []
    if df is None:
        return results
    for label, cols in candidates:
        try:
            dup = int(df.duplicated(cols, keep=False).sum())
            groups = int(df.duplicated(cols, keep=False).groupby(
                df[cols].astype(str).agg("|".join, axis=1)
            ).sum().gt(0).sum())
            results.append({
                "key_name": label,
                "columns": cols,
                "duplicate_rows": dup,
                "duplicate_groups": groups,
                "unique": dup == 0,
            })
        except Exception as e:
            results.append({
                "key_name": label,
                "columns": cols,
                "error": str(e),
            })
    return results

def duplicate_samples(df, cols, limit=25):
    if df is None or not cols:
        return []
    try:
        mask = df.duplicated(cols, keep=False)
        d = df.loc[mask, cols].copy()
        if d.empty:
            return []
        return d.drop_duplicates().head(limit).astype(str).to_dict("records")
    except Exception:
        return []

def schema_report(name, df):
    if df is None:
        return {"present": False}
    return {
        "present": True,
        "rows": int(len(df)),
        "columns": list(df.columns),
        "column_count": int(len(df.columns)),
        "key_evaluations": evaluate_keys(df, id_candidates(name, df)),
    }

def numeric_issues(df):
    issues = []
    if df is None:
        return issues
    for c in df.columns:
        s = pd.to_numeric(df[c], errors="coerce")
        if not s.notna().any():
            continue
        lc = norm(c)
        if any(x in lc for x in ["sdi", "percentile", "pct", "percent"]) and "per75" not in lc:
            bad = s[(s < -100) | (s > 100)]
            if len(bad):
                issues.append({
                    "column": c, "count": int(len(bad)),
                    "min": float(bad.min()), "max": float(bad.max())
                })
        if "sdi" in lc:
            bad = s[(s < 0) | (s > 100)]
            if len(bad):
                issues.append({
                    "column": c, "issue": "sdi_outside_0_100",
                    "count": int(len(bad)),
                    "min": float(bad.min()), "max": float(bad.max())
                })
    return issues

def career_qualification(df):
    if df is None:
        return {"status": "not_checked"}
    g = find_col(df, ["G", "Games"])
    mp = find_col(df, ["MP", "Minutes"])
    if not g or not mp:
        return {"status": "missing_required_columns", "columns": list(df.columns)}
    gg = pd.to_numeric(df[g], errors="coerce")
    mm = pd.to_numeric(df[mp], errors="coerce")
    q = (gg >= 400) & (mm >= 10000)
    return {
        "status": "checked",
        "rows": int(len(df)),
        "qualified": int(q.sum()),
        "not_qualified": int((~q).sum()),
        "rule": "G >= 400 and MP >= 10000"
    }

def json_structure(path):
    if not path:
        return {"status": "not_found"}
    payload = read_json(path)
    if payload is None:
        return {"status": "read_error"}
    if isinstance(payload, dict):
        keys = list(payload.keys())
        players = payload.get("players")
        if isinstance(players, list):
            return {
                "status": "checked",
                "top_level_keys": keys,
                "player_records": len(players),
                "first_player_keys": list(players[0].keys()) if players else [],
            }
        return {
            "status": "checked",
            "top_level_keys": keys,
            "player_records": None,
        }
    if isinstance(payload, list):
        return {
            "status": "checked",
            "top_level_type": "list",
            "records": len(payload),
            "first_record_keys": list(payload[0].keys()) if payload and isinstance(payload[0], dict) else [],
        }
    return {"status": "checked", "top_level_type": type(payload).__name__}

def named_player_presence(tables):
    out = {}
    for player in PLAYER_CHECKS:
        pdata = {}
        for name, df in tables.items():
            if df is None:
                continue
            p = player_col(df)
            if not p:
                continue
            rows = df[df[p].map(clean_name).str.casefold().eq(player.casefold())]
            if len(rows):
                s = season_col(rows)
                pdata[name] = {
                    "rows": int(len(rows)),
                    "seasons": [str(x) for x in rows[s].dropna().unique()[:30]] if s else []
                }
        out[player] = pdata
    return out

def wilt_cross_section(tables):
    """Extract Wilt PTS/75 values wherever the field exists."""
    out = {}
    for name, df in tables.items():
        if df is None:
            continue
        p = player_col(df)
        if not p:
            continue
        rows = df[df[p].map(clean_name).str.casefold().eq("wilt chamberlain")]
        if rows.empty:
            continue
        matches = [c for c in df.columns if norm(c) in {
            "pts_per75", "pts_75", "ptsper75", "pts_per_75"
        }]
        if not matches:
            matches = [c for c in df.columns if "pts" in norm(c) and "per75" in norm(c)]
        if matches:
            s = season_col(rows)
            out[name] = {
                "columns": matches,
                "values": rows[[x for x in ([s] if s else []) + matches]].astype(str).to_dict("records")
            }
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("website_root")
    args = ap.parse_args()

    root = Path(args.website_root).expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"Website root does not exist: {root}")

    paths = resolve_sources(root)
    csv_keys = ["master", "career_sdi", "regular_sdi", "playoff_sdi", "wowy", "percentiles"]
    tables = {k: read_csv(paths[k]) for k in csv_keys}

    report = {
        "phase": "Player Profile Data Integrity v3",
        "read_only": True,
        "website_root": str(root),
        "sources": {k: str(v) if v else None for k, v in paths.items()},
        "schemas": {k: schema_report(k, tables[k]) for k in csv_keys},
        "duplicate_samples": {},
        "numeric_issues": {k: numeric_issues(v) for k, v in tables.items()},
        "career_qualification": career_qualification(tables["career_sdi"]),
        "regular_peak_json_structure": json_structure(paths["regular_peak"]),
        "playoff_peak_json_structure": json_structure(paths["playoff_peak"]),
        "named_player_presence": named_player_presence(tables),
        "wilt_pts75_cross_section": wilt_cross_section(tables),
        "manual_followups": [
            "Determine whether Master duplicate player-season-type rows are legitimate multi-team/split rows or true duplicates.",
            "Determine the correct Playoff SDI identity key from its actual schema and duplicate samples.",
            "Inspect the actual Regular 5-Year Peak JSON structure and confirm five qualifying seasons within the six-calendar-season maximum span.",
            "Inspect the actual Playoff 5-Year Peak JSON structure and confirm its authoritative schema.",
            "Compare Wilt Chamberlain PTS/75 across Profile and Compare source layers.",
            "Verify Career SDI uses minutes-weighted WOWY values and the locked 60% block / 40% steal Defense Activity split.",
            "Verify Route A SDI remains primary and companion percentile is supplementary only.",
            "Verify canonical NBA CDN headshots are not overwritten by Basketball-Reference JPGs."
        ],
        "locked_rules": {
            "career_min_games": 400,
            "career_min_minutes": 10000,
            "regular_single_min_games_share": 0.60,
            "regular_single_min_minutes": 1400,
            "playoff_single_min_games": 4,
            "playoff_single_min_minutes": 75,
            "regular_peak_seasons": 5,
            "regular_peak_max_calendar_span": 6,
            "route_a_sdi_is_primary": True,
            "companion_percentile_does_not_replace_sdi": True,
        }
    }

    # Concrete duplicate samples for the two flagged datasets.
    for key in ["master", "playoff_sdi"]:
        df = tables[key]
        if df is None:
            continue
        evals = evaluate_keys(df, id_candidates(key, df))
        best = None
        # Select the first key that actually demonstrates duplication, otherwise
        # the most specific available key.
        for e in evals:
            if e.get("duplicate_rows", 0) > 0:
                best = e
                break
        if best is None and evals:
            best = evals[0]
        if best:
            report["duplicate_samples"][key] = {
                "evaluated_key": best["columns"],
                "duplicate_rows": best.get("duplicate_rows"),
                "samples": duplicate_samples(df, best["columns"])
            }

    out = root / "data" / "player_profile_data_integrity_report_v3.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("=" * 80)
    print("PLAYER PROFILE DATA INTEGRITY AUDIT v3")
    print("=" * 80)
    for k, v in report["sources"].items():
        print(f"{k:16} {v or 'NOT FOUND'}")
    print()
    for k, s in report["schemas"].items():
        print(f"{k:16} rows={s.get('rows')} columns={s.get('column_count')}")
        print(f"  key evaluations: {s.get('key_evaluations', [])[:4]}")
    print()
    print("DUPLICATE SAMPLES")
    for k, v in report["duplicate_samples"].items():
        print(f"{k}: key={v.get('evaluated_key')} duplicate_rows={v.get('duplicate_rows')}")
        for sample in v.get("samples", [])[:10]:
            print(" ", sample)
    print()
    print("PEAK STRUCTURES")
    print("regular_peak:", report["regular_peak_json_structure"])
    print("playoff_peak:", report["playoff_peak_json_structure"])
    print()
    print("WILT PTS/75 CROSS-SECTION")
    print(json.dumps(report["wilt_pts75_cross_section"], indent=2))
    print()
    print(f"Report: {out}")

if __name__ == "__main__":
    main()
