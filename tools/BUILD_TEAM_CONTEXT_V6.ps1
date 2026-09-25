# NBA PER-75 — Team Competitive Context V6
# Put land_standings_bundle.json and series.html in local_api\cache\, then run this file.
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Set-Location $root
python local_api\build_team_competitive_context_v6.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "`nTeam competitive context built successfully." -ForegroundColor Green
