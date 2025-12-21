@echo off
title Instagram Scraper
cd /d "%~dp0"

echo.
echo ========================================
echo   Instagram Reel Scraper API
echo ========================================
echo.

set AUTO_COOKIE_REFRESH=1
set INSTAGRAM_USERNAME=bhdemo2025
set INSTAGRAM_PASSWORD=passpass

echo Starting tunnel...
echo Look for URL below:
echo.

cloudflared.exe tunnel --url http://127.0.0.1:8000
