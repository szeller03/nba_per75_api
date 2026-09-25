"""
NBA PER-75 — Player Profile Data Integrity Audit v2

Schema-aware audit for Website241.

Key corrections versus v1:
- Player-season identity includes Season_Type when available.
- Long percentile tables are keyed by Player + Season + Statistic.
- Playoff SDI accepts alternate season/year columns.
- Regular 5-Year Peak authority is resolved from actual peak datasets, while
  authority-check JSON files are excluded from the peak-data selection.
- The audit is read-only except for its JSON report.
"""

from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import pandas as pd
import numpy as np

PLAYER_CHECKS = [
    "Wilt Chamberlain", "Michael Jordan", "LeBron James",
    "Kareem Abdul-Jabbar", "Hakeem Olajuwon", "Bill Russell",
    "Tim Duncan", "Kevin Garnett", "Shaquille O'Neal",
    "Nikola Jokic", "Patrick Ewing"
]

def norm(x):
    return re.sub(r"[^a-z0-9]+", "_", str(x).strip().lower()).strip("_")

def clean_name(x):
    return str(x).replace("*", "").strip()

def is_authority_check(path):
    n = path.name.lower()
    return "authority_check" in n or "authority-check" in n

def path_score(path, terms):
    n = path.name.lower()
    return sum(5 if t in n else 0 for t in terms)

def find_csv_candidates(root):
    return list(root.rglob("*.csv"))

def find_json_candidates(root):
    return list(root.rglob("*.json"))

def choose_file(root, terms, suffixes=(".csv", ".json"), exclude_terms=()):
    candidates = [
        p for p in (find_csv_candidates(root) + find_json_candidates(root))
        if p.suffix.lower() in suffixes
        and not any(t.lower() in p.name.lower() for t in exclude_terms)
    ]
    ranked = sorted(
        [(path_score(p, terms), -len(str(p)), p) for p in candidates],
        key=lambda x: (-x[0], x[1], str(x[2]).lower())
    )
    return ranked[0][2] if ranked and ranked[0][0] > 0 else None

def resolve_sources(root):
    # Prefer the known Website241 filenames/patterns.
    master = choose_file(root, ["nba_per75_master_v46", "nba_per75_master"])
    career = choose_file(root, ["regular_career_sdi_v4_wowy_rts", "career_sdi"])
    regular = choose_file(
        root,
        ["regular_sdi_v4_wowy_player_seasons", "regular_sdi"],
    )
    playoff = choose_file(
        root,
        ["playoff_sdi_v4_player_seasons", "playoff_sdi"],
    )
    regular_peak = choose_file(
        root,
        ["regular_profile_peaks_v2", "regular_profile_peaks",
         "regular_5_year_peak", "regular_peak"],
        exclude_terms=["authority_check"]
    )
    playoff_peak = choose_file(
        root,
        ["playoff_profile_peaks_authoritative_v9",
         "playoff_profile_peaks", "playoff_5_year_peak"],
    )
    wowy = choose_file(
        root,
        ["player_wowy_statistics_v1", "wowy_statistics"],
    )
    percentiles = choose_file(
        root,
        ["historical_percentiles_v2_1", "player_season_percentiles_long_v2_1",
         "historical_percentiles", "percentiles_long"],
    )
    return {
        "master": master,
        "career_sdi": career,
        "regular_sdi": regular,
        "playoff_sdi": playoff,
        "regular_peak": regular_peak,
        "playoff_peak": playoff_peak,
        "wowy": wowy,
        "percentiles": percentiles,
    }

def load_table(path):
    if not path:
        return None
    try:
        if path.suffix.lower() == ".json":
            return None
        return pd.read_csv(path, low_memory=False)
    except Exception:
        return None

def find_col(df, choices):
    if df is None:
        return None
    mapping = {norm(c): c for c in df.columns}
    for c in choices:
        if norm(c) in mapping:
            return mapping[norm(c)]
    return None

def identity_columns(name, df):
    if df is None:
        return []
    p = find_col(df, ["Player", "Player_Name", "Display_Name", "player_name"])
    s = find_col(df, [
        "Season", "season", "Season_ID", "SeasonId",
        "SeasonEndYear", "Season_End_Year", "Year", "year"
    ])
    st = find_col(df, ["Season_Type", "season_type", "SeasonType"])
    stat = find_col(df, [
        "Statistic", "statistic", "Stat", "Statistic_Name", "stat_name"
    ])

    if name == "percentiles":
        cols = [c for c in [p, s, stat] if c]
        # If the long table has season type, include it too.
        if st:
            cols.append(st)
        return cols

    cols = [c for c in [p, s] if c]
    if st:
        cols.append(st)
    return cols

def audit_table(name, df):
    out = {"present": df is not None, "rows": None, "issues": [],
           "identity_key": []}
    if df is None:
        out["issues"].append("source_not_found")
        return out

    out["rows"] = int(len(df))
    ids = identity_columns(name, df)
    out["identity_key"] = ids

    p = find_col(df, ["Player", "Player_Name", "Display_Name", "player_name"])
    if not p:
        out["issues"].append("missing_player_column")

    # Season is not mandatory for career-only datasets.
    if name not in ("career_sdi", "regular_peak", "playoff_peak"):
        if len(ids) < 2:
            out["issues"].append("missing_season_or_identity_column")

    if ids:
        dup = df.duplicated(ids, keep=False)
        out["duplicate_identity_rows"] = int(dup.sum())
        if dup.any():
            out["issues"].append("duplicate_identity")

    st = find_col(df, ["Season_Type", "season_type", "SeasonType"])
    if st:
        out["season_types"] = sorted(
            set(df[st].dropna().astype(str))
        )[:20]

    return out

def numeric_range_audit(df):
    issues = []
    if df is None:
        return issues

    for c in df.columns:
        s = pd.to_numeric(df[c], errors="coerce")
        if not s.notna().any():
            continue
        lc = norm(c)

        if any(k in lc for k in ["pct", "percentile"]) and "per75" not in lc:
            bad = s[(s < -100) | (s > 100)]
            if len(bad):
                issues.append({
                    "column": c,
                    "issue": "implausible_percentage_or_percentile",
                    "count": int(len(bad)),
                    "min": float(bad.min()),
                    "max": float(bad.max()),
                })

        if "sdi" in lc:
            bad = s[(s < 0) | (s > 100)]
            if len(bad):
                issues.append({
                    "column": c,
                    "issue": "sdi_outside_0_100",
                    "count": int(len(bad)),
                    "min": float(bad.min()),
                    "max": float(bad.max()),
                })
    return issues

def player_rows(df, player):
    if df is None:
        return pd.DataFrame()
    p = find_col(df, ["Player", "Player_Name", "Display_Name", "player_name"])
    if not p:
        return pd.DataFrame()
    target = clean_name(player).casefold()
    return df[df[p].map(clean_name).str.casefold().eq(target)].copy()

def inspect_named_players(tables):
    result = {}
    for player in PLAYER_CHECKS:
        item = {}
        for key, df in tables.items():
            rows = player_rows(df, player)
            if len(rows):
                entry = {"rows": int(len(rows))}
                s = find_col(rows, [
                    "Season", "season", "SeasonEndYear",
                    "Season_End_Year", "Year", "year"
                ])
                if s:
                    entry["seasons"] = [
                        str(x) for x in rows[s].dropna().unique()[:30]
                    ]
                item[key] = entry
        result[player] = item
    return result

def audit_career_qualification(df):
    if df is None:
        return {"status": "not_checked"}
    g = find_col(df, ["G", "Games"])
    mp = find_col(df, ["MP", "Minutes"])
    if not g or not mp:
        return {"status": "missing_required_columns"}

    gg = pd.to_numeric(df[g], errors="coerce")
    mm = pd.to_numeric(df[mp], errors="coerce")
    q = (gg >= 400) & (mm >= 10000)
    return {
        "status": "checked",
        "rows": int(len(df)),
        "qualified_rows": int(q.sum()),
        "subthreshold_rows": int((~q).sum()),
        "minimum_games": 400,
        "minimum_minutes": 10000,
    }

def audit_regular_peak(path):
    if not path:
        return {"status": "source_not_found"}
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return {"status": "read_error", "error": str(e)}
        players = payload.get("players", [])
        bad = []
        for p in players:
            seasons = p.get("peak_seasons", []) or []
            if len(seasons) != 5:
                bad.append({"player": p.get("player_name"),
                            "issue": "not_five_seasons"})
        return {
            "status": "checked_json",
            "players": len(players),
            "bad_peak_metadata_count": len(bad),
            "bad_peak_metadata": bad[:100],
        }

    df = load_table(path)
    if df is None:
        return {"status": "read_error"}
    p = find_col(df, ["Player", "Player_Name", "Display_Name", "player_name"])
    if not p:
        return {"status": "missing_player_column"}

    return {
        "status": "checked_table",
        "rows": int(len(df)),
        "player_count": int(df[p].nunique(dropna=True)),
        "columns": list(df.columns),
    }

def audit_peak_span(df):
    if df is None:
        return {"status": "not_checked"}
    p = find_col(df, ["Player", "Player_Name", "Display_Name", "player_name"])
    s = find_col(df, ["Season", "season"])
    start = find_col(df, ["Peak_Start_Year", "peak_start_year", "Start_Year"])
    end = find_col(df, ["Peak_End_Year", "peak_end_year", "End_Year"])
    if not p:
        return {"status": "missing_player_column"}
    out = {"status": "checked", "rows": int(len(df))}
    if start and end:
        a = pd.to_numeric(df[start], errors="coerce")
        b = pd.to_numeric(df[end], errors="coerce")
        bad = (b - a > 5)
        out["span_violations"] = int(bad.sum())
    else:
        out["span_check"] = "metadata columns not present"
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("website_root")
    args = ap.parse_args()
    root = Path(args.website_root).expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"Website root does not exist: {root}")

    paths = resolve_sources(root)
    tables = {k: load_table(v) for k, v in paths.items()}

    report = {
        "phase": "Player Profile Data Integrity v2",
        "read_only": True,
        "website_root": str(root),
        "sources": {k: str(v) if v else None for k, v in paths.items()},
        "table_audits": {
            k: audit_table(k, v) for k, v in tables.items()
        },
        "numeric_range_issues": {
            k: numeric_range_audit(v) for k, v in tables.items()
        },
        "career_qualification": audit_career_qualification(
            tables.get("career_sdi")
        ),
        "regular_peak": audit_regular_peak(paths.get("regular_peak")),
        "playoff_peak": audit_peak_span(tables.get("playoff_peak")),
        "named_player_presence": inspect_named_players(tables),
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
        },
        "manual_followups": [
            "Cross-check Wilt Chamberlain PTS/75 between Player Profile and Player Comparison.",
            "Cross-check WOWY Net/Offense/Defense across Profile data layers.",
            "Confirm Career SDI category boxes use NQ when the career does not qualify.",
            "Confirm TOV/75 and TOV% are lower-is-better in percentile calculations.",
            "Confirm NBA CDN portraits remain canonical and B-Ref JPGs do not override them.",
            "Do not alter Route A SDI values while adding companion percentiles.",
        ],
    }

    out = root / "data" / "player_profile_data_integrity_report_v2.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("=" * 80)
    print("PLAYER PROFILE DATA INTEGRITY AUDIT v2")
    print("=" * 80)
    for k, v in report["sources"].items():
        print(f"{k:16} {v or 'NOT FOUND'}")
    print()
    for k, v in report["table_audits"].items():
        print(f"{k:16} rows={v.get('rows')} key={v.get('identity_key')} issues={v.get('issues', [])}")
    print()
    print(f"Report: {out}")

if __name__ == "__main__":
    main()
