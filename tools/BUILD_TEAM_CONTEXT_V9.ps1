$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
python local_api/build_team_competitive_context_v9.py --interactive-fallback
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
