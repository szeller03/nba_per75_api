# SDI v4 corrected raw Career axis build

This build fixes the Player Profile Career SDI source path. Career category axes are rebuilt from the canonical career statistic-percentile layer using the locked regular-season subcategory weights, with canonical category-label aliases so Creation / Playmaking and Impact / Value are not dropped.

Regular Defense remains a six-category regular-season dimension and retains WOWY Defense. Playoff-only removal of Defense/Impact is not applied to regular season.

Career STL/BLK evidence is excluded from the Career Defense formula when underlying tracked minutes are below 50% of the player's career minutes; this prevents a one-season recorded BLK/STL rate from being treated as a career-wide measurement. WOWY Defense remains available independently.

The visible profile uses the raw category SDI score (`score`), not the companion population percentile.
