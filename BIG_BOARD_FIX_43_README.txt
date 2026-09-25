Website240 Performance Fix 43 — Big Board companion-path optimization

Purpose
-------
Keep the proven Fix 42 / Fix 36 Player Profile architecture locked while removing
Big Board's remaining legacy companion request path.

Changes
-------
1. Primary Regular Season Single-Season Big Board continues to use the compact
   public SQLite layer.
2. Companion-stat requests now use the same public layer and are restricted to
   the player IDs returned by the primary board. This removes the legacy
   /api/v1/big-board 100,000-row companion request that was visible in logs.
3. The public Big Board response now supplies season_options/seasons so the
   season selector has the same metadata it expects from the legacy path.
4. No changes to SDI, WOWY, qualification thresholds, percentile methodology,
   peak methodology, or Player Profile request/rendering behavior.

Install
-------
Replace the corresponding src/ and local_api/ files in Website240 with this
package. Do NOT run any database builder; this fix uses the existing public
SQLite layer.

Test
----
Start the API normally, open Big Board, and watch the log. Regular Season
single-season board requests should use /api/v1/public/big-board for both the
primary and companion statistics. There should no longer be a companion
/api/v1/big-board?....&limit=100000 request.
