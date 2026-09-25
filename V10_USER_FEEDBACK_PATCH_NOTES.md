# Website232 V10 — User Feedback Patch

- Kept the existing canonical NBA headshot registry as the primary player-photo source. Basketball-Reference is not used as the direct image CDN because its page photos are not exposed by the current app as the standardized transparent PNG asset.
- Added canonical historical team-logo files as the first team-logo source so local white-backed Logo_File assets are no longer preferred.
- Restored percentile visibility with text-only continuous color; no percentile boxes.
- Increased player-profile statistic values and six-dimension labels.
- Restored Big Board secondary stats to plain text with only percentile-derived text color.
- Rebuilt Player Comparison range controls into explicit A/B-aligned rows and changed dimension bars to two independent 0–100 bars.
- Fixed Explorer tooltip clipping and made the hover tooltip show player, season, X value, and Y value.
- Increased Create Your T75 portrait area while removing transform-based cropping.
