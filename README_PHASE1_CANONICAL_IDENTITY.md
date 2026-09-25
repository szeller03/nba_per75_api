# Phase 1 — Canonical Player Identity Repair

This package starts the **actual fix sequence** for the Player Profile data problems.

## What it fixes

The master data contains cases where one `Player_ID` is used for more than one real
player. The known examples include Charles Jones, Charles Smith, Eddie Johnson,
George Johnson, Tony Mitchell, and others.

The package creates a **canonical identity layer** without deleting records.

### Important

This is deliberately conservative:

- Regular Season and Playoffs remain separate.
- No source statistical rows are deleted.
- A same-name/ID collision is not silently guessed into one human.
- Ambiguous records are marked `AMBIGUOUS_SOURCE_COLLISION`.
- Clean records retain their existing Player_ID as the canonical ID.

## Run

From the website root:

```powershell
python local_api\build_canonical_player_identity_v1.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
python local_api\validate_canonical_player_identity_v1.py "C:\Users\szell\OneDrive\Desktop\NBA_Per75_Website241"
```

## Outputs

The script creates:

```text
data\player_identity\
    canonical_player_identity_v1.csv
    player_id_collision_groups_v1.csv
    identity_repair_report_v1.json
```

## What happens next

This identity layer is intended to become the input to the **playoff percentile
rebuild**, followed by playoff SDI regeneration.

This package does NOT rebuild playoff percentiles yet, because doing that before
establishing a stable identity crosswalk would risk assigning playoff percentiles
to the wrong human.

No production stat files are overwritten by this package.
