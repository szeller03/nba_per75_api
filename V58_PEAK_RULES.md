# NBA PER-75 Website V58 — Locked Peak Rules

## Regular-season playoff-independent rules
- Regular-season 5-Year Peak: five qualifying seasons within a maximum six-calendar-season span.
- One skipped/non-qualifying season is allowed; two consecutive skipped seasons are not.
- No Era Average threshold is applied to 5-Year Peak.
- Big Board regular 5-Year Peak is statistic-specific.
- Player Profile regular 5-Year Peak is one canonical SDI-selected window; all displayed statistics use that same window.
- Era filtering is available for peaks and is assigned by the peak starting season.

## Playoffs
- Single-season playoff percentile qualification changed to >=3 games AND >=75 minutes.
- Playoff all-time leaderboard remains >=7 games AND >=125 minutes.
- Playoff career remains >=50 games AND >=1,500 minutes.
- Playoff 5-Year Peak: exactly five consecutive playoff appearances, every appearance meeting the single-season 3 G + 75 MP threshold, with at least 35 total games across the five appearances.
- No missing postseason is allowed inside a playoff 5-Year Peak.
- Big Board playoff 5-Year Peak is statistic-specific.
- Player Profile playoff 5-Year Peak is a canonical window selected from season-level playoff Statistical Dominance Index values; all displayed peak statistics use that same five-appearance window.

## Important implementation repair
- Regular-season qualification season keys are normalized to the same YYYY-YY representation as master seasons. This fixes the prior V57 "No Big Board rows" / unavailable peak-profile condition caused by comparing numeric qualification years to formatted season labels.
