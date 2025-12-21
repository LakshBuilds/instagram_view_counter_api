@echo off
title Instagram Scraper - Simple Start
cd /d "%~dp0"

echo.
echo ========================================
echo   Instagram Reel Scraper
echo ========================================
echo.
echo Choose your option:
echo.
echo [1] Single Account API (FastAPI + Tunnel)
echo [2] Multi-Account Parallel Scraper
echo [3] One-Click Parallel Scraper
echo [4] No Delay Scraper (High Risk)
echo [5] Dashboard Monitor
echo.

set /p choice="Enter choice (1-5): "

if "%choice%"=="1" (
    echo Starting Single Account API...
    start "API Server" cmd /k "python api.py"
    timeout /t 3 /nobreak >nul
    start "Cloudflare Tunnel" cmd /k "cloudflared.exe tunnel --url http://127.0.0.1:8000"
) else if "%choice%"=="2" (
    echo Starting Multi-Account Parallel Scraper...
    python auto_run_parallel.py
) else if "%choice%"=="3" (
    echo Starting One-Click Parallel Scraper...
    python one_click_scraper.py
) else if "%choice%"=="4" (
    echo Starting No Delay Scraper...
    python no_delay_scraper.py
) else if "%choice%"=="5" (
    echo Starting Dashboard Monitor...
    python dashboard.py
) else (
    echo Invalid choice!
    pause
    goto :eof
)

pause