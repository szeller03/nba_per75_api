@echo off
cd /d "%~dp0"
call npm install
call npm run build
echo.
echo Performance Fix 32 build complete.
echo Start API: python local_api\nba_per75_local_api.py
echo Preview: npm run preview
pause
