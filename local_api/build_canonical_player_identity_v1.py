"""
Phase 1 — Canonical Player Identity Repair

Read-only diagnostic/repair-map builder. It does NOT overwrite production data.

Purpose:
- Detect Player_ID collisions in the master player-season table.
- Build a canonical identity map using the strongest identity fields available.
- Preserve separate people who share a Player_ID/name.
- Produce a crosswalk that downstream playoff percentile/SDI builders can use.

Usage:
    python local_api/build_canonical_player_identity_v1.py "C:\\path\\to\\NBA_Per75_Website241"

Outputs:
    data/player_identity/canonical_player_identity_v1.csv
    data/player_identity/player_id_collision_groups_v1.csv
    data/player_identity/identity_repair_report_v1.json

The script intentionally stops short of silently guessing a human identity when
the source data cannot distinguish two people. Ambiguous groups are marked
REVIEW rather than merged.
"""

from pathlib import Path
import json
import re
import sys
import pandas as pd


def norm(x):
    if pd.isna(x):
        return ""
    return re.sub(r"\s+", " ", str(x).strip()).lower()


def find_master(root):
    candidates = [
        root / "data" / "nba_per75_master_v46.csv",
        root / "data" / "nba_per75_master.csv",
    ]
    for p in candidates:
        if p.exists():
            return p
    matches = sorted((root / "data").glob("*master*.csv"))
    if matches:
        return matches[0]
    raise FileNotFoundError("Could not locate the master player-season CSV.")


def pick(df, names):
    low = {str(c).lower(): c for c in df.columns}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    master_path = find_master(root)
    out = root / "data" / "player_identity"
    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(master_path, low_memory=False)

    player_id = pick(df, ["Player_ID", "player_id"])
    player = pick(df, ["Player", "Player_Name", "player"])
    season = pick(df, ["Season", "season"])
    season_type = pick(df, ["Season_Type", "season_type", "Type"])
    age = pick(df, ["Age", "age"])
    team = pick(df, ["Team", "Tm", "team"])
    position = pick(df, ["Pos", "Position", "position"])
    games = pick(df, ["G", "Games", "games"])
    minutes = pick(df, ["MP", "Minutes", "minutes"])

    required = [player_id, player, season, season_type]
    if any(x is None for x in required):
        raise ValueError(
            f"Master is missing required identity columns. "
            f"Found Player_ID={player_id}, Player={player}, Season={season}, Season_Type={season_type}"
        )

    work = df.copy()
    work["_pid"] = work[player_id].map(norm)
    work["_player"] = work[player].map(norm)
    work["_season"] = work[season].map(norm)
    work["_stype"] = work[season_type].map(norm)
    work["_age"] = work[age].map(norm) if age else ""
    work["_team"] = work[team].map(norm) if team else ""
    work["_pos"] = work[position].map(norm) if position else ""

    # A statistical record identity is season-type aware. Do not collapse
    # regular season and playoffs.
    record_key = ["_pid", "_season", "_stype"]
    dup_groups = work.groupby(record_key, dropna=False).size()
    dup_groups = dup_groups[dup_groups > 1]

    collision_rows = []
    canonical_rows = []

    # A canonical candidate is based on the observed identity signature.
    # Player_ID alone is deliberately NOT treated as a unique human identity.
    for key, grp in work.groupby(record_key, dropna=False, sort=False):
        signature_cols = ["_player"]
        if age:
            signature_cols.append("_age")
        if team:
            signature_cols.append("_team")
        if position:
            signature_cols.append("_pos")

        signatures = grp[signature_cols].fillna("").astype(str).drop_duplicates()
        ambiguous = len(signatures) > 1

        # For ordinary groups, one canonical identity is sufficient.
        # For collisions, retain one identity candidate per distinct age/team/
        # position signature rather than dropping records.
        if ambiguous:
            for sig_no, (_, sg) in enumerate(grp.groupby(signature_cols, dropna=False, sort=False), 1):
                canonical_id = f"{key[0]}__candidate_{sig_no}"
                for _, r in sg.iterrows():
                    canonical_rows.append({
                        "Canonical_Player_ID": canonical_id,
                        "Player_ID": r[player_id],
                        "Player": r[player],
                        "Season": r[season],
                        "Season_Type": r[season_type],
                        "Age": r[age] if age else "",
                        "Team": r[team] if team else "",
                        "Position": r[position] if position else "",
                        "Identity_Status": "AMBIGUOUS_SOURCE_COLLISION",
                    })
                collision_rows.append({
                    "Player_ID": key[0],
                    "Season": key[1],
                    "Season_Type": key[2],
                    "Candidate": sig_no,
                    "Player": sg[player].iloc[0],
                    "Age": sg[age].iloc[0] if age else "",
                    "Teams": "|".join(sorted(set(sg[team].dropna().astype(str)))) if team else "",
                    "Positions": "|".join(sorted(set(sg[position].dropna().astype(str)))) if position else "",
                    "Games": sg[games].sum() if games else "",
                    "Minutes": sg[minutes].sum() if minutes else "",
                    "Identity_Status": "AMBIGUOUS_SOURCE_COLLISION",
                })
        else:
            canonical_id = key[0]
            for _, r in grp.iterrows():
                canonical_rows.append({
                    "Canonical_Player_ID": canonical_id,
                    "Player_ID": r[player_id],
                    "Player": r[player],
                    "Season": r[season],
                    "Season_Type": r[season_type],
                    "Age": r[age] if age else "",
                    "Team": r[team] if team else "",
                    "Position": r[position] if position else "",
                    "Identity_Status": "CANONICAL",
                })

    canonical = pd.DataFrame(canonical_rows)
    collisions = pd.DataFrame(collision_rows)

    # Summary of IDs that collide anywhere in the master.
    colliding_ids = sorted(set(collisions["Player_ID"])) if len(collisions) else []

    report = {
        "status": "REVIEW_REQUIRED" if colliding_ids else "PASS",
        "master": str(master_path),
        "rows": int(len(df)),
        "record_identity": ["Player_ID", "Season", "Season_Type"],
        "colliding_player_ids": colliding_ids,
        "collision_group_count": int(len(dup_groups)),
        "collision_candidate_rows": int(len(collisions)),
        "important_rule": "Player_ID is not assumed to be a unique human identity.",
        "production_changes": False,
        "next_step": "Use this identity layer when rebuilding playoff percentiles and playoff SDI; do not delete or merge ambiguous source records without an authoritative identity mapping."
    }

    canonical.to_csv(out / "canonical_player_identity_v1.csv", index=False)
    collisions.to_csv(out / "player_id_collision_groups_v1.csv", index=False)
    (out / "identity_repair_report_v1.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )

    print("CANONICAL PLAYER IDENTITY PHASE 1")
    print(f"Master: {master_path}")
    print(f"Rows: {len(df):,}")
    print(f"Collision groups: {len(dup_groups):,}")
    print(f"Colliding Player_IDs: {len(colliding_ids):,}")
    print(f"Status: {report['status']}")
    print(f"Output: {out}")


if __name__ == "__main__":
    main()
