@echo off
title Multi-Account Parallel Scraper
cd /d "%~dp0"

echo.
echo ========================================
echo   PARALLEL INSTAGRAM SCRAPER
echo ========================================
echo.
echo BEHAVIOR:
echo   - 3 accounts run in parallel
echo   - Each account: 20 reels with 15s delays
echo   - All accounts start simultaneously
echo   - Global wait: 5 minutes between cycles
echo ========================================
echo.

python auto_run_parallel.py

pause