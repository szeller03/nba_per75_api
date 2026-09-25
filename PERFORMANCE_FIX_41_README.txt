Website240 Performance Fix 41 — Frontend Request Orchestration

Purpose:
- Restore the known-good Fix 36/40 backend architecture.
- Reduce duplicate regular-season season-bundles requests.
- Make the regular-season profile critical path a single public season-bundles payload.
- Defer the optional Career spider until the profile has painted.
- Keep Playoff legacy behavior unchanged.
- Preserve all statistics, SDI/WOWY methodology, peak methodology, and headshot hierarchy.

This package contains the frontend source supplied for the Website240 performance audit.
Replace the corresponding src/ files in the current Website240 project.

No statistical source files or backend databases are included.
