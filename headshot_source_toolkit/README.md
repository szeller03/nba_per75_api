# NBA PER-75 — Historical Headshot Source Toolkit v1

Purpose: acquire **already-transparent PNG** historical player cutouts for players whose current NBA CDN image is a silhouette/placeholder or otherwise unsuitable.

This toolkit intentionally does **not** convert JPG photographs into transparent cutouts. That avoids the repeated background-removal/cropping failures in Website288–290.

## Source policy
1. Keep an existing confirmed NBA CDN portrait when it is suitable.
2. For a historical gap, search Wikimedia Commons for an exact player-name match and accept only image assets that are already PNGs with an alpha channel.
3. JPEG/WEBP candidates are recorded but **not** installed.
4. Nothing is automatically assigned to the website without a local visual review flag being cleared.

## Run
From the website root:

```powershell
python headshot_source_toolkit\acquire_transparent_png_candidates.py
```

Outputs:
- `headshot_source_toolkit\candidates\` — downloaded transparent PNG candidates
- `headshot_source_toolkit\candidate_manifest.csv` — player/source mapping
- `headshot_source_toolkit\needs_review.csv` — candidates requiring visual verification
- `headshot_source_toolkit\source_failures.csv` — players for whom no qualifying PNG was found

The script reads the project's canonical 4,896-player identity registry and targets the records already classified as needing headshot replacement.
